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

Some platform-dependant exceptions aside, assembly code maps onto binary machine instructions in a 1:1 manner.


Inline assembly
---------------

Modern, high-level languages exist primarily to free the programmer from having to hand-write (and optimize) assembly code for their machine. Since gaining direct access to assembly instructions is rarely worth losing the ability to write high-level code, [inline assembly](https://en.wikipedia.org/wiki/Inline_assembler) can be used to write small fragments of assembly embedded in the language of choice.


Syntax
------

Different (human-readable) assembly syntaxes can cause a lot of confusion, as they change not only the manner in which different values are written but also the order in which operands are given. When writing x86 assembly, there are two widely used variations of assembly syntax available: [Intel and AT&T](http://www.imada.sdu.dk/Courses/DM18/Litteratur/IntelnATT.htm). Given the task of writing the value `0x1F` (31 in decimal) into the `eax` register, a programmer would have to write

```text
mov    eax, 1fh
```

in Intel syntax and 

```text
movl   %eax, $0x1f
```

in AT&T syntax.

Of note is that not only are the instructions named slightly different ---
`mov` vs `movl` --- but values prefixed in AT&T. Even specifying hexadecimal numbers works different between these two. To complete the confusion, argument order is reversed as well: The destination (`eax`) is specified first in Intel syntax while being last in AT&T syntax.

Fortunately in this article we will not have to chose either one. ARM assembly usually uses a syntax different from both of these and manages to be more readable:

```text
mov    r0, #0x1f
```

General purpose registers in ARM assembly are named `r0` through `r16` (or higher/lower) instead of `eax`, ... and only literal values (called
*immediates*) are prefixed.

An important fact to remember is that the assembly syntax changes depending on the platform and compiler backend when writing inline assembly. Inline assembly in Rust on the ARM platform uses the ARM-syntax mentioned above.
