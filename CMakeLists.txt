cmake_minimum_required(VERSION 3.16)
project(DRNAS_Native_X1_X2 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
add_executable(drnas-x1 src/drnas_x1.cpp)
add_executable(drnas-x2 src/drnas_x2.cpp)
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(drnas-x1 PRIVATE -O3 -Wall -Wextra -Wpedantic)
  target_compile_options(drnas-x2 PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

add_executable(drnas-x3 src/drnas_x3.cpp)
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(drnas-x3 PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

add_executable(drnas-x4 src/drnas_x4.cpp)
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(drnas-x4 PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

add_executable(drnas-x41 src/drnas_x41.cpp)
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(drnas-x41 PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()

# Identical CDCL source for a frozen comparison and an opt-in capacity guard.
# Missing optional crypto headers do not prevent building the existing targets.
add_executable(drnas-pcmax-base src/drnas_x5.cpp)
find_package(OpenSSL QUIET COMPONENTS Crypto)
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-pcmax src/drnas_x5.cpp)
  target_compile_definitions(drnas-pcmax PRIVATE DRNAS_PCMAX_MODULE)
  target_link_libraries(drnas-pcmax PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-pcmax PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
else()
  message(STATUS "OpenSSL Crypto not found: optional drnas-pcmax target unavailable")
endif()
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(drnas-pcmax-base PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()


# Independent MG7 proof-first experiment. Both arms use the same unchanged
# CDCL source; only the opt-in experiment target compiles residual SCC logic.
add_executable(drnas-mg7-base src/drnas_x5.cpp)
add_executable(drnas-mg7-scc src/drnas_x5.cpp)
target_compile_definitions(drnas-mg7-scc PRIVATE DRNAS_RESIDUAL_SCC)
if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(drnas-mg7-base PRIVATE -O3 -Wall -Wextra -Wpedantic)
  target_compile_options(drnas-mg7-scc PRIVATE -O3 -Wall -Wextra -Wpedantic)
endif()


# Single-process combined mathematical pre-gate and original CDCL + residual SCC.
# The two certificate formats are intentionally distinct: capacity JSON must be
# checked with the structural checker and original-source VeriPB; CDCL uses DRAT.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-pcmax-mg7-unified src/drnas_x5.cpp)
  target_compile_definitions(drnas-pcmax-mg7-unified PRIVATE
    DRNAS_PCMAX_MODULE DRNAS_RESIDUAL_SCC DRNAS_PC_GUARD_COMBINED)
  target_link_libraries(drnas-pcmax-mg7-unified PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-pcmax-mg7-unified PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()


# IPG1 exact integer-cover proof-first experiment, opt-in only.
# No portfolio or subprocess: BDD -> integer-cover -> CDCL+residual SCC.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-pcmax-mg7-ipg1 src/drnas_x5.cpp)
  target_compile_definitions(drnas-pcmax-mg7-ipg1 PRIVATE
    DRNAS_PCMAX_MODULE DRNAS_RESIDUAL_SCC DRNAS_PC_GUARD_COMBINED
    DRNAS_IPG1_MODULE)
  target_link_libraries(drnas-pcmax-mg7-ipg1 PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-pcmax-mg7-ipg1 PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()


# IPG-BDD1 polynomial count-profile research: source-grounded native exporter.
# The executable ONLY exports graph premises, never returns SAT/UNSAT.
# Subsequent Python producer/checker remain strictly experimental.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-ipg-bdd-extract research/ipg_bdd_extract.cpp)
  target_link_libraries(drnas-ipg-bdd-extract PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-ipg-bdd-extract PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()


# IPG-BDD2: all prior native guards + exact two-class BDD count profiles.
# Same process / one logical CPU, with explicit source-bound structural proof.
# Non-IPG-BDD2 targets keep their frozen behavior.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-pcmax-mg7-ipg1-bdd2 src/drnas_x5.cpp)
  target_compile_definitions(drnas-pcmax-mg7-ipg1-bdd2 PRIVATE
    DRNAS_PCMAX_MODULE DRNAS_RESIDUAL_SCC DRNAS_PC_GUARD_COMBINED
    DRNAS_IPG1_MODULE DRNAS_IPG_BDD2_MODULE)
  target_link_libraries(drnas-pcmax-mg7-ipg1-bdd2 PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-pcmax-mg7-ipg1-bdd2 PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()


# IPG-BDD3 three-class source-count native target, isolated experimental branch.
# No change to frozen older targets; each SAT solver remains one process/CPU.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-pcmax-mg7-ipg1-bdd3 src/drnas_x5.cpp)
  target_compile_definitions(drnas-pcmax-mg7-ipg1-bdd3 PRIVATE
    DRNAS_PCMAX_MODULE DRNAS_RESIDUAL_SCC DRNAS_PC_GUARD_COMBINED
    DRNAS_IPG1_MODULE DRNAS_IPG_BDD2_MODULE DRNAS_IPG_BDD3_MODULE)
  target_link_libraries(drnas-pcmax-mg7-ipg1-bdd3 PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-pcmax-mg7-ipg1-bdd3 PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()


# IPG5-B source-bound structural proof research executable.
# One native C++ process/CPU, no CDCL; emits RUP needing external VeriPB.
# Frozen sources and all old solver targets remain unchanged.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-ipg5b-jobbranch research/ipg5b_native_jobbranch.cpp)
  target_link_libraries(drnas-ipg5b-jobbranch PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-ipg5b-jobbranch PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()


# IPG5-C experimental general source-onehot bounded C++ RUP generator.
# Emits proof only after complete native source-RUP replay; arbitrary source
# SHA must be checked by an external independently committed manifest.
# No CDCL, no main, no new concurrent worker.
if (TARGET OpenSSL::Crypto)
  add_executable(drnas-ipg5c-onehot research/ipg5c_native_onehot.cpp)
  target_link_libraries(drnas-ipg5c-onehot PRIVATE OpenSSL::Crypto)
  if (CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(drnas-ipg5c-onehot PRIVATE -O3 -Wall -Wextra -Wpedantic)
  endif()
endif()
