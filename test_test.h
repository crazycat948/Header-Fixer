#ifndef TEST_ADD_H
#define TEST_ADD_H

#ifdef __cplusplus
extern "C" {
#endif

#include <limits.h>
#include <stdint.h>
#include "unity.h"

int add(int a, int b);

void test_add_add_param(void);

#ifdef __cplusplus
}
#endif

#endif /* TEST_ADD_H */