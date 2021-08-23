#include <tuple>
#include <unistd.h>

#include "error.h"

std::tuple<pid_t, int, int> exec_with_pipe(const char *const command)
{
	int pipe_to_proc[2], pipe_from_proc[2];

	pipe(pipe_to_proc);
	pipe(pipe_from_proc);

	pid_t pid = fork();
	if (pid == 0) {
		setsid();

		close(0);

		dup(pipe_to_proc[0]);
		close(pipe_to_proc[1]);
		close(1);
		close(2);
		dup(pipe_from_proc[1]);
		dup(pipe_from_proc[1]);
		close(pipe_from_proc[0]);

		int fd_max = sysconf(_SC_OPEN_MAX);
		for(int fd=3; fd<fd_max; fd++)
			close(fd);

		if (execlp(command, command, nullptr) == -1)
			error_exit(true, "Failed to invoke %s", command);
	}

	close(pipe_to_proc[0]);
	close(pipe_from_proc[1]);

	std::tuple<pid_t, int, int> out(pid, pipe_to_proc[1], pipe_from_proc[0]);

	return out;
}
