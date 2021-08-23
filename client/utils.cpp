#include <errno.h>
#include <stdarg.h>
#include <string>
#include <unistd.h>

#include "error.h"

int WRITE(int fd, const char *whereto, size_t len)
{
        ssize_t cnt=0;

        while(len > 0)
        {
                ssize_t rc = write(fd, whereto, len);
                if (rc <= 0)
                        return rc;

		whereto += rc;
		len -= rc;
		cnt += rc;
	}

	return cnt;
}

std::string myformat(const char *fmt, ...)
{
	char *buffer = NULL;
        va_list ap;

        va_start(ap, fmt);
        (void)vasprintf(&buffer, fmt, ap);
        va_end(ap);

	std::string result = buffer;
	free(buffer);

	return result;
}
