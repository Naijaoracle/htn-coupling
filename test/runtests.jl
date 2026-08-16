using HTNCoupling
using Test

@test length(HTNCoupling.OPENBF_REVISION) == 40
@test all(isxdigit, HTNCoupling.OPENBF_REVISION)
