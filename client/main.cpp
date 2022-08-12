#include <getopt.h>
#include <poll.h>
#include <signal.h>
#include <stdio.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>

#include "error.h"
#include "proc.h"
#include "sock.h"
#include "utils.h"

void print_time()
{
	struct timeval tv;
	gettimeofday(&tv, nullptr);

	struct tm *tm = localtime(&tv.tv_sec);

	char buffer[128];
	strftime(buffer, 128, "%Y:%m:%d %H:%M:%S", tm);
	printf("%s.%03ld ", buffer, tv.tv_usec / 1000);
}

void help(void)
{
	printf("-e x  program to invoke (Ataxx \"engine\")\n");
	printf("-i x  server to connect to\n");
	printf("-p x  port to connect to (usually 28028)\n");
	printf("-U x  username to use\n");
	printf("-P x  password to use\n");
	printf("-v    verbose output\n");
}

int main(int argc, char **argv)
{
	const char *proc = nullptr;
	const char *host = "server.ataxx.org";
	int port = 28028;
	int c = -1;
	const char *user = nullptr, *password = nullptr;
	bool verbose = false;

	while((c = getopt(argc, argv, "i:p:e:U:P:vh")) != -1) {
		switch(c) {
			case 'i':
				host = optarg;
				break;

			case 'p':
				port = atoi(optarg);
				break;

			case 'e':
				proc = optarg;
				break;

			case 'U':
				user = optarg;
				break;

			case 'P':
				password = optarg;
				break;

			case 'v':
				verbose = true;
				break;

			case 'h':
				help();
				return 0;

			default:
				help();
				return 1;
		}
	}

	if (!proc)
		error_exit(false, "No program to run given");

	if (!user || !password)
		error_exit(false, "No username/password");

	for(;;) {
		int s = -1;

		do {
			s = connect_to(host, port);

			if (s == -1)
				sleep(1);
		}
		while(s == -1);

		set_nodelay(s);
		set_keepalive(s);

		std::string user_str = myformat("user %s\r\n", user);
		if (WRITE(s, user_str.c_str(), user_str.size()) <= 0) {
			fprintf(stderr, "Failed sending username to server\n");
			close(s);
			s = -1;
			continue;
		}

		std::string password_str = myformat("pass %s\r\n", password);
		if (WRITE(s, password_str.c_str(), password_str.size()) <= 0) {
			fprintf(stderr, "Failed sending password to server\n");
			close(s);
			s = -1;
			continue;
		}

		auto prc = exec_with_pipe(proc);

		struct pollfd fds[2] = { { s, POLLIN, 0 }, { std::get<2>(prc), POLLIN, 0 } };

		for(;;) {
			char buffer[65536];

			fds[0].revents = fds[1].revents = 0;

			if (poll(fds, 2, -1) == -1)
				error_exit(true, "poll() failed");

			if (fds[0].revents == POLLIN) {
				int rc = read(fds[0].fd, buffer, sizeof(buffer) - 1);
				if (rc == -1)
					error_exit(true, "read error from socket");

				if (rc == 0) {
					fprintf(stderr, "Socket closed\n");
					break;
				}

				if (verbose) {
					buffer[rc] = 0x00;
					print_time();
					printf("%s] Server: %s", host, buffer);
				}

				rc = WRITE(std::get<1>(prc), buffer, rc);
				if (rc == -1)
					error_exit(true, "write fail to program");
				if (rc == 0) {
					fprintf(stderr, "program has gone away\n");
					break;
				}
			}

			if (fds[1].revents == POLLIN) {
				int rc = read(fds[1].fd, buffer, sizeof(buffer) - 1);
				if (rc == -1)
					error_exit(true, "read error from program");

				if (rc == 0) {
					fprintf(stderr, "Program closed\n");
					break;
				}

				if (verbose) {
					buffer[rc] = 0x00;
					print_time();
					printf("%s] Program: %s", user, buffer);
				}

				rc = WRITE(fds[0].fd, buffer, rc);
				if (rc == -1)
					error_exit(true, "write fail to socket");
				if (rc == 0) {
					fprintf(stderr, "socket closed\n");
					break;
				}
			}
		}

		kill(SIGTERM, std::get<0>(prc));
		close(std::get<1>(prc));
		close(std::get<2>(prc));

		int wstatus = 0;
		if (waitpid(-1, &wstatus, WNOHANG) == 0) {
			sleep(1);
			kill(SIGKILL, std::get<0>(prc));
		}

		int exit_status = 0;
		wait(&exit_status);

		close(s);

		sleep(1);
	}

	return 0;
}
