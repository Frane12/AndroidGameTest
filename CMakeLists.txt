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
