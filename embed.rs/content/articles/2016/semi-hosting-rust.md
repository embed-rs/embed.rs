---
{
  "date": "2016-10-18T12:36:00+02:00",
  "title": "Semi-hosting on ARM with Rust",
  "author_ids": [ "mbr" ],
  "contributor_ids": [ ],
  "draft": true,
  "tags": [
    "rust",
    "embedded",
    "assembly",
    "semi-hosting",
    "arm"
  ],
  "discussion": [

  ]

}
---

If a technology is in use for two decades and still has no Wikipedia entry, it seems safe to call it "a bit obscure". *Semi-hosting* is such a technology and can be a great help in debugging boards with no [IO](https://en.wikipedia.org/wiki/Input/output) facilities other than a [JTAG](https://en.wikipedia.org/wiki/JTAG) or another debugging port available.

When developing firmware for an embedded board, `println!`-style (or `printf`-style for more *C*-affine readers) debugging can be immensely useful, a quick-fix that can save a lot of time that would otherwise be spent setting breakpoints or single-stepping through a program. Being able to output text does require IO ports of some sort though, be it USB, networking or another connection to the [MCU](https://en.wikipedia.org/wiki/Microcontroller) that the code is being run on. But the mere presence of these ports is not enough, without drivers they cannot be used, creating a classic chicken-and-egg problem when implementing said drivers.

There is a way around the issue: During bare-metal development, uploading new program code is often handled through a targets debugging facilities, which should include a way to set breakpoints, halt the CPU and explore memory contents as well. These functionalities can be (and have been) twisted into a full-blown RPC mechanism, as shown below.


Semi-hosting, step-by-step
--------------------------

*Semi-hosting* refers to making some of the *host*'s (i.e. the computer running the debugger) functionality available to the *target*, the MCU being debugged, through the debugger itself.

1. The target executes a **breakpoint** instruction with a special tag.
2. The debugging-software on the host is **notified** of the breakpoint.
3. Information inside the **first two registers** indicates which procedure should be called and points to a structure with arguments.
4. The debugger uses its memory-reading capabilities to **retrieve the arguments** and passes these on to the host's procedure.
5. The target's CPU is unhalted by the debugger and **execution continues**.


ARMv6 and ARMv7
---------------

The exact process is instruction set specific, for example ARMv6 and ARMv7 use a `bkpt` instruction, while some other ARM instruction sets use an `svc` (*supervisor command*) instruction. This article will assume an ARM Cortex-M series MCU, which is using the ARMv7 style breakpoints. Additionally, instead of using any of the commercial debugging software solutions, [gdb](https://en.wikipedia.org/wiki/GNU_Debugger) will be used as the debugger. We can now implement the process step-by-step:


### Halting the CPU

A simple `bkpt 0xAB` inline assembly instruction is enough to halt the CPU (see the [inline assembly introduction](http://embed.rs/articles/2016/arm-inline-assembly-rust) for help on the `asm!`-macro):

```rust
asm!("bkpt 0xAB");
```

The parameter `0xAB` is a magic-number taken from the [official documentation](http://infocenter.arm.com/help/index.jsp?topic=/com.arm.doc.dui0471g/Bgbjjgij.html), it does not have any effect on the target, neither is it passed along when the CPU halts. Instead, the debugger is expected to find the current instruction by reading the program counter and looking it up inside the binary, then to check which value is passed. If it is `0xAB`, the breakpoint is interpreted as a semi-hosting call.

We can now try this in gdb: A remote-debugger has been started and this is what happens when the MCU executes the `bkpt` instruction:

```
Program received signal SIGTRAP, Trace/breakpoint trap.
0x080102e4 in hello_embed_rs::_rust_start::hfb6a6b3dc95a15dd ()
(gdb)
```

Verifying the program counter is indeed at `0x80102e4`:

```
(gdb) p/x $pc
$1 = 0x80102e4
```

Checking the disassembly, we know that all the information we need is readily available. Note that the Thumb-Instruction set uses 2-byte instructions instead of 4:

```
(gdb) disassemble 0x80102e4,+2
Dump of assembler code from 0x80102e4 to 0x80102e6:
=> 0x080102e4 <...>:bkpt  0x00ab
End of assembler dump.
```


### Implementing the `SVC_WRITE` call

The [`SVC_WRITE`](http://infocenter.arm.com/help/index.jsp?topic=/com.arm.doc.dui0471g/Bacbedji.html) call is specified by the ARM compiler toolchain to write arbitrary data to a file descriptor on the host. The general calling convention for semi-hosting calls is as follows:

* `r0` must contain the number indicating the type of call.
* `r1` is a pointer to a struct containing arguments for the call.
* Each call has its own struct format.
* A call can return either a single 32-bit integer or an address, both of which
  are stored in `r0` afterwards.

The ID associated with `SVC_WRITE` is `0x05`, it must be moved into register `r0`. Furthermore a parameter struct is necessary:

```rust
#[repr(C)]
struct SvcWriteCall {
    // the file descriptor on the host
    fd: usize,
    // pointer to data to write
    addr: *const u8,
    // length of data to write
    len: usize,
}
```

Armed with this definition, we can implement the SVC-calling function:

```rust
unsafe fn call_svc(num: usize, addr: *const ()) -> usize {
    // allocate stack space for the possible result
    let result: usize;

    // move type and argument into registers r0 and r1, then trigger
    // breakpoint 0xAB. afterwards, save a potential return value in r0
    asm!("mov r0,$1\n\t\
          mov r1,$2\n\t\
          bkpt 0xAB\n\t\
          mov $0,r0"
        : "=ri"(result)
        : "ri"(num), "ri"(addr)
        : "r0", "r1"
        : "volatile"
       );

    // return result (== r0)
    result
}
```

The `"volatile"` option indicates that the code has side-effects and should not be by removed by optimizations. The whole function is marked `unsafe`, because we are dereferencing the `addr` pointer, albeit the host does our dirty work.

With the capability to perform arbitrary SVC-calls, we implement the `SYS_WRITE` function by placing the argument structure on the stack, then passing a pointer to it to `call_svc`.

```rust
const SYS_WRITE: usize = 0x05;

/// Semi-hosting: `SYS_WRITE`. Writes `data` to file descriptor `fd`
/// on the host. Returns `0` on success or number of unwritten bytes
/// otherwise.
fn svc_sys_write(fd: usize, data: &[u8]) -> usize {
    let args = SvcWriteCall {
        fd: fd,
        addr: data.as_ptr(),
        len: data.len(),
    };

    unsafe { call_svc(SYS_WRITE,
                      &args as *const SvcWriteCall as *const ()) }
}
```

The function is safe because all the parameters passed to `call_svc` are constant values or valid pointers; ensuring that the host's software does not have any bugs that corrupt our memory is outside the scope of our application.

Calling `svc_sys_write` inside `main()`:

```rust
// fd 2 is stderr:
svc_sys_write(2, b"Hello from Rust.\n");
```

Running the code again causes a `SIGTRAP` in gdb:

```
Program received signal SIGTRAP, Trace/breakpoint trap.
0x080102e4 in hello_embed_rs::_rust_start::hfb6a6b3dc95a15dd ()
```

Inspecting `r0` and `r1`

```
(gdb) p/x $r0
$1 = 0x5
(gdb) p/x $r1
$2 = 0x2002ffc8
```

confirms that `r0` has the correct value of `0x05`, while `r1` points us to `0x2002ffc8`, which should be a three word structure:

```
(gdb) p *0x2002ffc8
$3 = 2
(gdb) p/x *(0x2002ffc8+4)
$4 = 0x8010008
(gdb) p *(0x2002ffc8+8)
$5 = 17
```

The first field is our file-descriptor `2`. The second is the address of the string to be printed, note that it is not inside the RAM area (`0x200xxxxxx`), but pointing to the flash memory (`0x080xxxxx`). The string constant is read directly from the binary! The third field denotes the `17` characters.

We can now print the string:

```
(gdb) printf "%17s", 0x08010008
Hello from Rust.
```