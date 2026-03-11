#ifndef __DEBUG_H
#define __DEBUG_H
#include <stdio.h>
#define Debug(__info, ...) printf(__info, ##__VA_ARGS__)
#endif
