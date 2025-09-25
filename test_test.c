#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <stdint.h>
#include "unity.h"

int add(int a, int b);

static void add_param_check(int in_a, int in_b, int out_expected)
{
    long long wide_sum = (long long)in_a + (long long)in_b;
    if (wide_sum < INT_MIN || wide_sum > INT_MAX) {
        TEST_IGNORE_MESSAGE("Sum outside representable int range; skip to avoid undefined behavior.");
        return;
    }
    TEST_ASSERT_EQUAL_INT((int)wide_sum, out_expected);
    int result = add(in_a, in_b);
    TEST_ASSERT_EQUAL_INT(out_expected, result);
}

void test_add_add_param(void)
{
    add_param_check(1, 2, 3);
    add_param_check(-1, -2, -3);
    add_param_check(0, 0, 0);
    add_param_check(INT_MAX, 0, INT_MAX);
    add_param_check(INT_MIN, 0, INT_MIN);
    /* This case will be ignored because it overflows the int range */
    add_param_check(INT_MAX, 1, 0);
}