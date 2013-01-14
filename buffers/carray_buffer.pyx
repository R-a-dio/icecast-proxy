from libc.stdlib cimport malloc, free
from libc.string cimport memcpy
from posix.unistd cimport usleep
cimport openmp


cdef class Buffer:
    cdef unsigned char * read_ptr, * write_ptr
    cdef int max_size, length
    cdef int eof
    cdef unsigned char * buffer
    cdef unsigned char * out_buffer
    
    cdef openmp.omp_lock_t write_lock
    cdef openmp.omp_lock_t read_lock
    cdef openmp.omp_lock_t length_lock
    def __cinit__(Buffer self, unsigned int max_size):
        self.max_size = max_size
        self.length = 0
        self.eof = 0
        
        cdef unsigned char * buffer = <unsigned char *>malloc(max_size * sizeof(char))
        self.buffer = buffer
        self.read_ptr = buffer
        self.write_ptr = buffer
        
        cdef unsigned char * temp_buffer = <unsigned char *>malloc(max_size * sizeof(char))
        self.out_buffer = temp_buffer
        
        openmp.omp_init_lock(&self.write_lock)
        openmp.omp_init_lock(&self.read_lock)
        openmp.omp_init_lock(&self.length_lock)
        
        
    def write(self, data):
        self.cwrite(data, len(data))
        
    cdef object cwrite(Buffer self, unsigned char * data, unsigned int data_length):
        cdef unsigned int available_space = 0
        cdef unsigned int write_pos
        with nogil:
            if data_length > self.max_size:
                data += data_length - self.max_size
                data_length = self.max_size
                
            # thread safety
            openmp.omp_set_lock(&self.write_lock)
            
            # end thread safety
            write_pos = self.write_ptr - self.buffer
            
            if (write_pos + data_length) > self.max_size:
                # Do our first copy
                available_space = self.max_size - write_pos
                memcpy(self.write_ptr, data, available_space)
                # Reset write pointer to front
                self.write_ptr = self.buffer
                # Increase pointer of incoming data
                data += available_space
                
                # Get ready for second copy
                available_space = data_length - available_space
                
                memcpy(self.write_ptr, data, available_space)
                
                # Increase writer
                self.write_ptr += available_space
                
            else:
                # Just one copy is all we need
                memcpy(self.write_ptr, data, data_length)
                self.write_ptr += data_length
                
            # Anything after setting the new length is not thread-safe with the reader.
            # Thus we have to lock it if we want to do anything afterwards.
            if (self.length + data_length) > self.max_size:
                # The buffer is overflowing with data so we have to push the
                # reader forwards. (and thus need to lock it)
                openmp.omp_set_lock(&self.read_lock)
                
                self.read_ptr = self.write_ptr
                
                openmp.omp_set_lock(&self.length_lock)
                self.length = self.max_size
                openmp.omp_unset_lock(&self.length_lock)
                
                
                openmp.omp_unset_lock(&self.read_lock)
            else:
                # We don't need to touch the reader so it is thread safe already
                # I lied the length needs a sync.
                openmp.omp_set_lock(&self.length_lock)
                self.length += data_length
                openmp.omp_unset_lock(&self.length_lock)
            # thread safety
            openmp.omp_unset_lock(&self.write_lock)
            # end thread safety
            
            
    def read(self, size):
        if size > self.max_size:
            size = self.max_size
        return self.cread(size)
        
    cdef bytes cread(Buffer self, unsigned int size):
        cdef unsigned int available_data = 0
        cdef unsigned int read_pos
        cdef unsigned char * out_buffer = self.out_buffer
        if self.eof and self.length == 0:
            # Quick fail here if we are already at end of file.
            return b''
            
        with nogil:
            while (self.length < size) and (not self.eof):
                usleep(100)
                
            if self.length < size:
                # This means we got closed.
                # Reset ourself to the length so we don't go out of bounds.
                size = self.length
            # thread safety
            openmp.omp_set_lock(&self.read_lock)
            # end thread safety
            
            read_pos = self.read_ptr - self.buffer
            if (read_pos + size) > self.max_size:
                # Prepare first copy over

                available_data = self.max_size - read_pos
                
                memcpy(out_buffer, self.read_ptr, available_data)
                # reset our pointer sicne we reached the end
                self.read_ptr = self.buffer
                # Increase the out one.
                out_buffer += available_data
                
                # Second copy time
                available_data = size - available_data
                
                memcpy(out_buffer, self.read_ptr, available_data)
                
                self.read_ptr += available_data
            else:
                # Simple one copy over
                memcpy(out_buffer, self.read_ptr, size)
                
                self.read_ptr += size
                
            # Ha you wanted atomic? NO!
            openmp.omp_set_lock(&self.length_lock)
            self.length -= size
            openmp.omp_unset_lock(&self.length_lock)
            
            # thread safety
            openmp.omp_unset_lock(&self.read_lock)
            # end thread safety
            
        return out_buffer[:size]
            
    def __len__(Buffer self):
        return self.length
        
    def __repr__(Buffer self):
        return "<Buffer size='{:s}' max_length='{:s}'>".format(self.max_size,
                                                               self.length)
        
    cpdef object close(Buffer self):
        self.eof = 1
        
    def __dealloc__(Buffer self):
        free(<void *>self.buffer)
        free(<void *>self.out_buffer)
        
        openmp.omp_destroy_lock(&self.write_lock)
        openmp.omp_destroy_lock(&self.read_lock)
        openmp.omp_destroy_lock(&self.length_lock)