cmake_minimum_required(VERSION 3.25)
project(nx2_lab VERSION 0.0.1 LANGUAGES CXX)

add_library(nx2core STATIC src/cpu.cpp src/memory.cpp src/owned_image.cpp src/owned_service.cpp)
target_include_directories(nx2core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(nx2core PUBLIC cxx_std_23)
if(MSVC)
  target_compile_options(nx2core PRIVATE /W4 /WX)
else()
  target_compile_options(nx2core PRIVATE -Wall -Wextra -Wpedantic -Werror)
endif()

add_executable(nx2lab src/main.cpp)
target_link_libraries(nx2lab PRIVATE nx2core)

include(CTest)
if(BUILD_TESTING)
  add_executable(nx2_cpu_test tests/cpu_test.cpp)
  target_link_libraries(nx2_cpu_test PRIVATE nx2core)
  add_test(NAME source_owned_aarch64_contract COMMAND nx2_cpu_test)
  add_test(NAME source_owned_cpu_demo COMMAND nx2lab demo)
  add_test(NAME source_owned_memory_demo COMMAND nx2lab memory-demo)
  add_test(NAME source_owned_executable_demo COMMAND nx2lab run-owned
    ${CMAKE_CURRENT_SOURCE_DIR}/fixtures/owned-aarch64-demo.nx2o)
  add_executable(nx2_service_stop_test tests/service_stop_test.cpp)
  target_link_libraries(nx2_service_stop_test PRIVATE nx2core)
  add_test(NAME source_owned_service_stop_contract COMMAND nx2_service_stop_test)
  add_test(NAME source_owned_service_stop_image COMMAND nx2lab run-owned
    ${CMAKE_CURRENT_SOURCE_DIR}/fixtures/owned-aarch64-service.nx2o)
  add_executable(nx2_image_test tests/owned_image_test.cpp)
  target_link_libraries(nx2_image_test PRIVATE nx2core)
  add_test(NAME source_owned_executable_image_contract COMMAND nx2_image_test)
  add_executable(nx2_memory_test tests/memory_test.cpp)
  target_link_libraries(nx2_memory_test PRIVATE nx2core)
  add_test(NAME source_owned_guest_memory_contract COMMAND nx2_memory_test)
  find_package(Python3 3.9 COMPONENTS Interpreter)
  if(Python3_Interpreter_FOUND)
    add_test(NAME source_owned_fixture_cli_contract COMMAND
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/owned_fixture_test.py
      $<TARGET_FILE:nx2lab>)
    add_test(NAME evidence_manifest_contract COMMAND
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_evidence.py
      ${CMAKE_CURRENT_SOURCE_DIR}/evidence/owned-aarch64-fixture.json)
    add_test(NAME evidence_memory_manifest COMMAND
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_evidence.py
      ${CMAKE_CURRENT_SOURCE_DIR}/evidence/owned-aarch64-memory.json)
    add_test(NAME evidence_executable_manifest COMMAND
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_evidence.py
      ${CMAKE_CURRENT_SOURCE_DIR}/evidence/owned-executable-v1.json)
    add_test(NAME evidence_service_manifest COMMAND
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tools/verify_evidence.py
      ${CMAKE_CURRENT_SOURCE_DIR}/evidence/owned-service-stop-v1.json)
    add_test(NAME evidence_negative_cases COMMAND
      ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/evidence_negative_test.py)
  endif()
endif()
