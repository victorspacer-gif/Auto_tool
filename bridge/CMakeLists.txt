cmake_minimum_required(VERSION 3.20)
project(studiomem_bridge LANGUAGES CXX ASM_MASM)

add_library(studiomem_bridge SHARED
    studiomem_bridge.cpp
    driver_adapter.cpp
    dbvm_adapter.cpp
    dbvm_vmcall.asm
)

target_compile_features(studiomem_bridge PRIVATE cxx_std_17)
target_compile_definitions(studiomem_bridge PRIVATE UNICODE _UNICODE WIN32_LEAN_AND_MEAN NOMINMAX)

if(MSVC)
    target_compile_options(studiomem_bridge PRIVATE /W4 /permissive-)
endif()
