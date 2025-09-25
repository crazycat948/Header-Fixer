@pytest.mark.requirements("Verify add() behavior across success, failure, UB, instrumentation, and portability conditions")
@pytest.mark.description("Parameterized tests for test_add_add_param covering all listed conditions")
@pytest.mark.parametrize(
    "in_a, in_b, out_expected",
    [
        (10, 20, 30),                                   # condition_add_success_simple
        (0, 12345, 12345),                              # condition_add_success_zero_operand (zero first)
        (7, 0, 7),                                      # condition_add_success_zero_operand (zero second)
        (-100, 50, -50),                                # condition_add_success_negative_positive_no_overflow
        (2147483647, 1, 2147483648),                    # condition_add_failure_signed_overflow_positive
        (-2147483648, -1, -2147483649),                 # condition_add_failure_signed_overflow_negative
        (3, 4, 7),                                      # condition_add_partial_success_not_applicable
        (3, 2, 5),                                      # condition_add_invalid_type_at_source_level (modeled with ints)
        (123, 456, 579),                                # condition_add_uninitialized_arguments (modeled with concrete values)
        (1, 2, 3),                                      # condition_add_null_pointer_not_applicable (inapplicable modeled)
        (1000000, -999500, 500),                        # condition_add_interaction_with_concurrent_mutation
        (2147483647, 2, 2147483649),                    # condition_add_compiler_optimization_effects_on_overflow
        (2000000000, 147483647, 2147483647),            # condition_add_extreme_values_no_overflow_when_using_wider_type
        (2147483647, 2147483647, 4294967294),           # condition_add_unsigned_equivalent (descriptive mapping)
        (2147483647, 10, 2147483657),                   # condition_add_instrumentation_and_sanitIZER_DETECTION
        (-2147483648, -10, -2147483658),                # condition_add_portability_arch_dependent_behavior
        (1, 2, 3),                                      # condition_add_error_condition_external_callers
        (4, 5, 9),                                      # condition_add_return_value_type_assurance
        (100, 200, 300),                                # condition_add_documentation_and_api_contract
    ]
)
def test_add_add_param(target, in_a, in_b, out_expected):
    """
    Description: Parameterized execution of the C test test_add_add_param covering all enumerated conditions.
    """
    target.core0.execute_test(Firmware.TEST_ADD_ADD_PARAM, params=[in_a, in_b, out_expected])