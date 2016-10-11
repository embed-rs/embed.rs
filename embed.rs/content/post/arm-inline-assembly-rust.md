+++
date = "2016-10-10T17:09:35+02:00"
title = "Exploring ARM inline assembly in Rust"
draft = true

+++

Inline assembly in modern languages is easily forgotten in day-to-day programming; its use has been diminished by having excellent compilers that produce equivalent or better code than what most programmers can hand-optimize. Outside of the field of optimization there are still some legitimate reasons to write a couple of instructions of assembly even then: Accessing CPU features that are platform-specific or simply not covered by compiler or library vendors.

This article gives a short introduction into inline assembly in Rust. It focuses on embedded development, more specifically the [ARM](https://en.wikipedia.org/wiki/ARM_architecture) architecture, which has a good reputation for being clear and also a lot of application in the embedded world, where one is much more likely to find oneself reaching for an assembler than on the desktop world of [x86-64](https://en.wikipedia.org/wiki/X86-64).


What is assembly?
=================

Compiling a valid Rust program ultimately yields a binary than can be executed. The process of generating one includes multiple steps that are hidden from the programmer:

![Rust source to machine code. See https://blog.rust-lang.org/2016/04/19/MIR.html for more details](/post/arm-inline-assembly-rust_01.svg)

The red section happens inside the Rust compiler which turns Rust source code into [LLVM](http://llvm.org/) *intermediate representation* (IR). The LLVM IR can be thought of as language-agnostic; C-code compiled with [clang](http://clang.llvm.org/) will end up as LLVM IR the same way as Rust code does at one point during compilation. After generation, the intermediate representation will be optimized and turned into the machine code that ends up inside the final binary.

Binary or numerical machine code refers to a set of instructions the target CPU can directly execute, with each instruction being coded numerically; e.g. adding two operands in ARM assembly is represented by the [opcode](https://en.wikipedia.org/wiki/Opcode) `0100`. Since these are hard to read, a text-based representation is avaiablable: [Assembly code](https://en.wikipedia.org/wiki/Assembly_language). Addition becomes `ADD` instead of
`0100` and operands can be specified a little easier as well. Some platform-dependant exceptions aside, assembly code maps onto binary machine instructions in a 1:1 manner.

Modern, high-level languages exist primarily to free the programmer from having to hand-write (and optimize) assembly code for their machine. Since gaining direct access to assembly instructions is rarely worth losing the ability to write high-level code, **[inline assembly](https://en.wikipedia.org/wiki/Inline_assembler)** can be used to write small fragments of assembly embedded in the language of choice.


Syntax
------

The different (human-readable) assembly syntaxes can cause a lot of confusion, as they change not only the manner in which different values are written but also the order in which operands are given. When writing x86 assembly, there are two widely used variations of assembly syntax available: [Intel and AT&T](http://www.imada.sdu.dk/Courses/DM18/Litteratur/IntelnATT.htm). Given the task of writing the value `0x1F` (31 in decimal) into the `eax` register, a programmer would have to write

```x86asm
mov    eax, 1fh
```

in Intel syntax and 

```attasm
movl   $0x1f, %eax
```

in AT&T syntax.

Of note is that not only are the instructions named slightly different ---
`mov` vs `movl` --- but values prefixed in AT&T. Even specifying hexadecimal numbers works different between these two. To complete the confusion, argument order is reversed as well: The destination (`eax`) is specified first in Intel syntax while being last in AT&T syntax.

Fortunately in this article we will not have to chose either one. ARM assembly usually uses a syntax different from both of these and manages to be more readable:

```armasm
mov    r0, #0x1f
```

General purpose registers in ARM assembly are named `r0` through `r16` (or higher/lower) instead of `eax`, ... and only literal values (called
*immediates*) are prefixed with a hash (`#`).

An important fact to remember is that the assembly syntax changes depending on the platform and compiler backend. Inline assembly in Rust on the ARM platform uses the ARM-syntax mentioned above.


The example program
===================


The following program solves the simple problem of finding the midway point between two other points that will be stored in `r0` through `r3`. More precisely, given two vectors $\mathbf{A} := \begin{bmatrix} x_1 \\\\ y_1 \end{bmatrix}$ and $\mathbf{B} := \begin{bmatrix} x_2 \\\\ y_2 \end{bmatrix}$, we want to calculate the midpoint vector $\\mathbf{M} := A + \\frac{(\\mathbf{B}-\\mathbf{A})}{2} = \frac{\\mathbf{A}+\\mathbf{B}}{2}$.

Our initial algorithm is simple: First, we store all values in registers,

(Notation: $a \\leftarrow b$ is the same as "in $a$, store $b$")

<ol start="1">
<li>$r_0 \leftarrow x_1$</li>
<li>$r_1 \leftarrow y_1$</li>
<li>$r_2 \leftarrow x_2$</li>
<li>$r_3 \leftarrow y_2$</li>
</ol>

before adding the components together

<ol start="5">
<li>$r_0 \leftarrow r_0 + r_2$</li>
<li>$r_1 \leftarrow r_1 + r_3$</li>
</ol>

and diving each component by two

<ol start="7">
<li>$r_0 \leftarrow \frac{r_0}{2}$</li>
<li>$r_1 \leftarrow \frac{r_1}{2}$</li>
</ol>

This translates directly into assembly code:

```armasm
;      we are looking for the midpoint-pixel between two points
;      A := (5, 6) and B := (15, 27)
;      expected result M: = (10, 16)

;      store A in r0 and r1
mov    r0, #5
mov    r1, #6

;      store B in r2 and r3
mov    r2, #15
mov    r3, #27

;      add both together
add    r0, r0, r2
add    r1, r1, r3

;      divide by two. since there is no division opcode on many ARMs,
;      we bitshift to the right
asr    r0, r0, #1
asr    r1, r1, #1

;      the end result of M := (10, 16) is now in r0, r1
```


The assembly code above will be used without comments further down. A fun way to try it out is using [Salman Arif's VisUAL](http://salmanarif.bitbucket.org/visual) ARM emulator.

# Running Rust ARM code on x86

If you are not writing code on a [Raspberry Pi](https://www.raspberrypi.org/) the chance that you are already working on an ARM machine are pretty slim. To keep things simple, we will write the example on an x86 machine using [cross-compilation](https://en.wikipedia.org/wiki/Cross_compiler). First, we use [rustup](https://www.rustup.rs/) to install the necessary `arm-unknown-linux-gnueabihf`target:

```sh
$ rustup target install arm-unknown-linux-gnueabihf
```

Now we can create a binary using Cargo with the following `main.rs`

```rust
#![feature(asm)]

fn main() {
    println!("Calculating...");

    unsafe {
        asm!("mov r0, #5
              mov r1, #6
              mov r2, #15
              mov r3, #27
              add r0, r0, r2
              add r1, r1, r3
              asr r0, r0, #1
              asr r1, r1, #1");
    }

    println!("Done");
}
```

and compile it (make sure you are on a nightly compiler):

```sh
$ cargo build --target=arm-unknown-linux-gnueabihf
```

It should build okay.

## Actually running it

To run the foreign binary, we can take two approaches. First, we could copy the program to an ARM system like the Raspberry Pi or a virtual machine and execute it from there. Second, if we are lucky enough to be programming on a Linux-machine, there is a convenient way of running non-native binaries directly using [QEMU User Emulation](https://wiki.debian.org/QemuUserEmulation).

Assuming user mode emulation is installed, we can run our program like any other and have it tell us we did something wrong immediately:

```text
$ cargo run --target=arm-unknown-linux-gnueabihf
    Finished debug [unoptimized + debuginfo] target(s) in 0.0 secs
     Running `target/arm-unknown-linux-gnueabihf/debug/example-arm-asm`
Calculating...
qemu: uncaught target signal 11 (Segmentation fault) - core dumped
error: Process didn't exit successfully: `target/arm-unknown-linux-gnueabihf/debug/example-arm-asm` (signal: 11, SIGSEGV: invalid memory reference)
```

# The `asm!` macro

Looking at the `asm!` macro, whose [rather sparse documentation](https://doc.rust-lang.org/book/inline-assembly.html) prompted the writing of this article, we see that it has the following syntax:

```rust
asm!(assembly template
   : output operands
   : input operands
   : clobbers
   : options
   );
```

Any amount of trailing `:` is optional, so far our example code has just been using the `assembly template` part.

## clobbering

Now it is time to look at the reason why our program crashed. Disassembling our code using `arm-none-eabi-objdump -D target/arm-unknown-linux-gnueabihf/debug/example-arm-asm`, we get the following output (showing only relevant lines):

```text
    ...
    3778:    e3a00005     mov    r0, #5
    377c:    e3a01006     mov    r1, #6
    3780:    e3a0200f     mov    r2, #15
    3784:    e3a0301b     mov    r3, #27
    3788:    e0800002     add    r0, r0, r2
    378c:    e0811003     add    r1, r1, r3
    3790:    e1a000c0     asr    r0, r0, #1
    3794:    e1a010c1     asr    r1, r1, #1
    3798:    e5901000     ldr    r1, [r0]
    ...
```

The first eight lines are the example code written above. Following the control flow, we see `ldr` loads data into the register `r1`, using an address stored `r0` --- which was just overwritten with the result the algorithms output!

This is known as *clobbering* --- by writing to registers without letting the compiler know about what we are doing, we have introduced undefined behaviour which will most likely result in a crash, as it did above.

To remedy, we can give a comma-separated list of registers that the assembly-code will use and the compiler will take care to structure all of its own calculations in a way that conflicts are avoided:


```
asm!("mov r0, #5
      mov r1, #6
      mov r2, #15
      mov r3, #27
      add r0, r0, r2
      add r1, r1, r3
      asr r0, r0, #1
      asr r1, r1, #1"
    :                          // no outputs yet
    :                          // no inputs yet
    :  "r0", "r1", "r2", "r3"  // clobbers
    :                          // no options
);
```

Looking at the disassembly output again, we see that the contents of `r0` are saved on the stack before our code runs and restored after:

```armasm
    3778:    e58d0008     str    r0, [sp, #8]
    ...
    379c:    e59d0008     ldr    r0, [sp, #8]

```

The example program now runs without crashing.

## output

To make the code above even slightly useful, we will need to be able to collect its output values. For this, the `output` parameter of the `asm!` macro can be used. In inline assembly, *operand expressions* are used to tell the compiler which variables should hold the end result of a calculation.

Getting a good reference about these is hard --- Rust passes these on to LLVM [(docs)](http://llvm.org/docs/LangRef.html#inline-assembler-expressions) almost unchanged, which in turn bases its syntax on GCC [(docs)](https://gcc.gnu.org/onlinedocs/gcc/Extended-Asm.html#Extended-Asm), but there are some non-obvious differences.

Our simple example case is fortunately not complicated: We want to save the contents of registers `r0` and `r1` in two variables, which we will call `m_x` and `m_y`. For these, a type-annotated declaration must be introduced beforehand and the following `asm!` macro call changed:

```rust
let m_x: u32;
let m_y: u32;

unsafe {
    asm!("mov r0, #5
          mov r1, #6
          mov r2, #15
          mov r3, #27
          add r0, r0, r2
          add r1, r1, r3
          asr r0, r0, #1
          asr r1, r1, #1"
        :  "={r0}" (m_x), "={r1} "(m_y)  // outputs
        :                                // no inputs yet
        :  "r0", "r1", "r2", "r3"        // clobbers
        :                                // no options
    );
}
```

The syntax for specifying outputs is as follows:

```
'"' constraint '"' '(' variableName ')'
```

All output constraints start with a "=" (write) or "+" (read and write). `"={r0}"` restricts the placement to the register `r0`, it is wrapped in curly braces because otherwise single-letter values would be expected at the position.

The actual variable follows in parenthesis after the constraint. `m_x` and `m_y` are the obvious values here.

Note that this output declaration is not very clean or flexible, as it forces the compiler to place our outputs exactly inside `r0` and `r1`. A better way is to use template names and allow more flexible placement:

```rust
let m_x: u32;
let m_y: u32;

unsafe {
    asm!("mov $0, #5
          mov $1, #6
          mov r2, #15
          mov r3, #27
          add $0, $0, r2
          add $1, $1, r3
          asr $0, $0, #1
          asr $1, $1, #1"
        :  "=r"(m_x), "=r"(m_y)  // outputs
        :                        // no inputs yet
        :  "r2", "r3"            // clobbers
        :                        // no options
    );
}

    println!("Result M: ({}, {})", m_x, m_y);
```

Instead of specifying a value, we replaced every occurence of `r0` with `$0`. The `$0` specifies that the first operand is to be used (the count starts at 0 with the first output constraint, with input constraints being counted last). The restriction `"=r"(m_x)` indicates that said first operand is an output operand that needs to be kept in a register (`"=r"`) and will be available in the variable `m_x`. The second operand is declared the same way.

The compiler can now choose which registers to use instead of `r0` and `r1`, which have disappeared from the assembly and the clobber list.

Running the program yields the expected result:

```text
Result M: (10, 16)
```

## input

Only getting outputs is still not sufficient, we want to be able to input things as well. Input operands work similar to output operands, sans the leading `=`:

```rust

let a_x = 5u32;
let a_y = 6u32;

let b_x = 15u32;
let b_y = 27u32;

// ...

asm!("mov $0, $2
      mov $1, $3
      mov r2, $4
      mov r3, $5
      add $0, $0, r2
      add $1, $1, r3
      asr $0, $0, #1
      asr $1, $1, #1
      "
    :  "=r"(m_x), "=r"(m_y)                    // outputs
    :  "r"(a_x), "r"(a_y), "r"(b_x), "r"(b_y)  // inputs
    :  "r2", "r3"                              // clobbers
    :                                          // no options
);
```

The code above will compile, but the result will be wrong:

```
Result M: (5, 16)
```

This is because the program violated one of the [requirements of LLVMs inline assembly](http://llvm.org/docs/LangRef.html#output-constraints):

> Normally, it is expected that no output locations are written to by the assembly expression until all of the inputs have been read. As such, LLVM may assign the same register to an output and an input. If this is not safe (e.g. if the assembly contains two instructions, where the first writes to one output, and the second reads an input and writes to a second output), then the “&” modifier must be used (e.g. “=&r”) to specify that the output is an “early-clobber” output. Marking an output as “early-clobber” ensures that LLVM will not use the same register for any inputs (other than an input tied to this output).

In other words, LLVM will freely use a register that we wanted to read input from as the output register in our assembly code. While occasionally hard to notice, this is easily fixed by reordering the template

```rust
asm!("mov r2, $4
      mov r3, $5
      mov $0, $2
      mov $1, $3
      ...
      "
// ...
```

We can optimize the code further though: Since we require all of our input variables to be in registers (via `"r"` constraints) already, it is possible to get rid of the initial `mov` instructions. We do need to mark them as "early-clobber" though, as we are using an output register at the same time as an input register (e.g. `$0` and `$2`):

```rust
unsafe {
    asm!("add $0, $2, $4
          add $1, $3, $5
          asr $0, $0, #1
          asr $1, $1, #1
          "
        :  "=&r"(m_x), "=&r"(m_y)                  // outputs
        :  "r"(a_x), "r"(a_y), "r"(b_x), "r"(b_y)  // inputs
        :                                          // clobbers
        :                                          // no options
    );
```

## Wrapping up

Using a data strucuture and moving the inline assembly inside a function cleans up the code nicely:

```rust
#![feature(asm)]

#[derive(Clone, Copy, Debug)]
struct Point {
    x: u32,
    y: u32,
}

/// Calculate the midpoint between two points `a` and `b`.
fn calc_midpoint(a: Point, b: Point) -> Point {
    let m_x: u32;
    let m_y: u32;

    unsafe {
        asm!("add $0, $2, $4
              add $1, $3, $5
              asr $0, $0, #1
              asr $1, $1, #1
              "
            :  "=&r"(m_x), "=&r"(m_y)                  // outputs
            :  "r"(a.x), "r"(a.y), "r"(b.x), "r"(b.y)  // inputs
            :                                          // clobbers
            :                                          // no options
        );
    }

    Point { x: m_x, y: m_y }
}

fn main() {
    let a = Point { x: 5, y: 6 };
    let b = Point { x: 15, y: 27 };

    let m = calc_midpoint(a, b);

    println!("Midpoint between A := {:?} and B := {:?} is:", a, b);
    println!("M = {:?}", m);
}
```

Inline assembly is tricky to get right and the documentation has a bit of a patchwork feel, especially if one is spoiled by the excellent material that is Rust's other documentation. Sometimes, though, there is no way around a few lines of inline assembly - a situation we will explore in another article.

*Written by [Marc Brinkmann](https://github.com/mbr). Many thanks to Oliver Schneider and [Philip Oppermann](http://phil-opp.com).*

<!-- note: MathJax code should be moved to the theme at some point-->
<script type="text/javascript"
  src="https://cdn.mathjax.org/mathjax/latest/MathJax.js?config=TeX-AMS-MML_HTMLorMML">
</script>

<script type="text/x-mathjax-config">
MathJax.Hub.Config({
  tex2jax: {
    inlineMath: [['$','$'], ['\\(','\\)']],
    displayMath: [['$$','$$'], ['\[','\]']],
    processEscapes: true,
    processEnvironments: true,
    skipTags: ['script', 'noscript', 'style', 'textarea', 'pre'],
    TeX: { equationNumbers: { autoNumber: "AMS" },
         extensions: ["AMSmath.js", "AMSsymbols.js"] }
  }
});
</script>

<script type="text/x-mathjax-config">
  MathJax.Hub.Queue(function() {
    // Fix <code> tags after MathJax finishes running. This is a
    // hack to overcome a shortcoming of Markdown. Discussion at
    // https://github.com/mojombo/jekyll/issues/199
    var all = MathJax.Hub.getAllJax(), i;
    for(i = 0; i < all.length; i += 1) {
        all[i].SourceElement().parentNode.className += ' has-jax';
    }
});
</script>
