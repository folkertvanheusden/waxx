CXXFLAGS=-Ofast -Wall
OBJS=proc.o error.o sock.o utils.o main.o

all: aclient

aclient: $(OBJS)
	$(CXX) -o aclient $(OBJS)

clean:
	rm -f aclient $(OBJS)
