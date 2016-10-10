+++
date = "2016-10-10T17:09:35+02:00"
title = "ARM inline assembly in Rust"
draft = true

+++

Inline assembly in modern languages is easily forgotten in day-to-day programming; its use has been diminished by compilers improving and often producing equivalent or better code than hand-optimized assembly. Still there remains a valid use case for assembly outside of optimization: Accessing CPU features that are platform-specific or otherwise unavailable.

This article gives a short introduction into inline assembly in Rust. It focuses on embedded development. or more specific the [ARM](https://en.wikipedia.org/wiki/ARM_architecture) architecture. Requiring access to a niche instruction on an embedded platform is much more likely than on the ubiquitous [x86-64](https://en.wikipedia.org/wiki/X86-64).

What is assembly?
=================

Compiling a valid Rust program ultimately yields a binary than can be executed. The process of generating one includes multiple steps that are hidden from the programmer:

![Rust source to machine code. See https://blog.rust-lang.org/2016/04/19/MIR.html for more details](/post/arm-inline-assembly-rust_01.svg)

The red section happens inside the Rust compiler which turns Rust source code into [LLVM](http://llvm.org/) *intermediate representation* (IR). The LLVM IR can be thought of as language-agnostic; C-code compiled with [clang](http://clang.llvm.org/) will end up as LLVM IR the same way as Rust code does at one point during compilation. After generation, the intermediate representation will be optimized and turned into machine code, found inside the resulting binary.

Binary or numerical machine code refers to a set of instructions the target CPU can directly execute, with each instruction being coded numerically; e.g. adding two operands in ARM assembly is represented by the [opcode](https://en.wikipedia.org/wiki/Opcode) `0100`. Since these are hard to read, a text-based representation is avaiablable: [Assembly code](https://en.wikipedia.org/wiki/Assembly_language). Addition becomes `ADD` instead of
`0100` and operands can be specified a little easier as well.

In general assembly code maps onto binary machine instructions in a 1:1 fashion, with some platform-dependant exceptions for convenience.
