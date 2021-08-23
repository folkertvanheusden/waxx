#include <tuple>
#include <unistd.h>

std::tuple<pid_t, int, int> exec_with_pipe(const char *const command);
