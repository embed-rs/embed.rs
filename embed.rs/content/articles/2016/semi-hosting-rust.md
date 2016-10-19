---
{
  "date": "2016-10-18T12:36:00+02:00",
  "title": "Semi-hosting on ARM with Rust",
  "author_ids": [ "mbr" ],
  "contributor_ids": [ "phil-opp" ],
  "tags": [
    "rust",
    "embedded",
    "assembly",
    "semi-hosting",
    "arm"
  ],
  "discussion": [
    ["/r/rust", "https://www.reddit.com/r/rust/comments/58botg/semihosting_on_arm_with_rust/"],
    ["Hacker News", "https://news.ycombinator.com/item?id=12746033"]
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


On ARM Cortex-M
---------------

The exact process is instruction set specific, for a Cortex-M in Thumb mode uses a `bkpt` instruction while other ARM instruction sets use an `svc` (*supervisor command*) or another instruction. Additionally, instead of using any of the commercial debugging software solutions, [gdb](https://en.wikipedia.org/wiki/GNU_Debugger) will be used as the debugger. We can now implement the process step-by-step:


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

The [`SVC_WRITE`](http://infocenter.arm.com/help/index.jsp?topic=/com.arm.doc.dui0471g/Bacbedji.html) call is specified by the ARM compiler toolchain to write arbitrary data to a file descriptor on the host. The general calling convention for any semi-hosting call is as follows:

* `r0` must contain the number indicating the type of call.
* `r1` is a pointer to a struct containing arguments for the call.
* Each call has its own struct format.
* A call can return either a single 32-bit integer or an address, both of which
  are stored in `r0` afterwards.

We can implement a generic SVC-calling function first:

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

To implement `SVC_WRITE`, whose ID is `0x05`, we also need a parameter struct (pointed to by `addr`):

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

We implement the `SYS_WRITE` function by placing the argument structure on the stack, then passing a pointer to it to `call_svc`.

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


Scripting the debugger
----------------------

After finishing the target's code, the next step is implementing a little script for the debugger to make things easier. Gdb supports Python scripting, so we will start with a few lines of Python to retrieve the current stack frame and *inferior*, gdb's term for the target, instance. Then, it is time to decode the assembly instruction and check if it is a `bkpt`:

```python
# get the current frame and inferior
frame = gdb.selected_frame()
inf = gdb.selected_inferior()

# retrieve instruction
ins = frame.architecture().disassemble(frame.pc())[0]
m = re.match(r'^bkpt\s+((?:0x)?[0-9a-f]+)$', ins['asm'].lower())
```

Afterwards, we check the immediate we saved using the regular expression and compare it to `0xAB`:

```python
if m:
    raw = m.group(1)
    # we've matched a breakpoint, decode the immediate
    bkpt_n = int(raw, 0)

    # breakpoint 0xab indicates a semi-hosting call
    if bkpt_n == 0xAB:
       # ...
```

Finally, we retrieve the register contents of `r0` and `r1` and call the appropriate handler:

```python
# retrieve the call type and obj registers
# note: we would like to use `Frame.read_registers()` for this,
#       but its only available on gdb 7.8 or newer
r0 = gdb.parse_and_eval('$r0')
r1 = gdb.parse_and_eval('$r1')

call_type = int(r0)
arg_addr = int(r1)

if call_type == 0x05:
    cls.handle_write(inf, arg_addr)
else:
    raise NotImplementedError(
        'Call type 0x{:X} not implemented'.format(call_type))
```

We will later combine all the code into a single class.

### Handling `SYS_WRITE`

The `handle_write` method needs to be implemented as well:

```python
# security, only allow fds 1 (stdout) and 2 (stderr)
SANE_FDS = (1, 2)

# whether or not to automatically continue execution
CONTINUE = True

# argument struct has three u32 entries: fd, address, len
buf = inf.read_memory(args_addr, 12)
fd, addr, l = struct.unpack('<lll', buf)

# limit length to 4M to avoid funky behavior
l = min(l, 4 * 1024 * 1024)

# sanity check file descriptor
if fd not in cls.SANE_FDS:
    raise ValueError(
        'Refusing to write to file descriptor {} (not in {})'.format(
            fd, cls.SANE_FDS))
```

Even if it is only intended to be executed during debugging using a closed system, access to arbitrary file descriptors or unchecked length reads should make the security-conscious hair on the back of your neck stand-up; for this reason we check all arguments for sanity and limit what is written to four megabytes.

Once we are sure our arguments are good, we can progress to read the string and print it:
```python
# read the memory
data = bytes(inf.read_memory(addr, l))

# we manually map FDs. encoding is fixed at the rust-native utf8
if fd == 1:
    sys.stdout.write(data.decode('utf8'))
elif fd == 2:
    sys.stderr.write(data.decode('utf8'))

if cls.CONTINUE:
    gdb.execute('continue')
```

An automatic continue is triggered as well if desired.

### The final class

All the code gets combined into a `SemiHostHelper` class:

```python
from __future__ import print_function
import gdb
import re
import struct
import sys


class SemiHostHelper(object):
    SANE_FDS = (1, 2)
    CONTINUE = True

    @classmethod
    def on_break(cls):
        # get the current frame and inferior
        frame = gdb.selected_frame()
        inf = gdb.selected_inferior()

        # retrieve instruction
        ins = frame.architecture().disassemble(frame.pc())[0]
        m = re.match(r'^bkpt\s+((?:0x)?[0-9a-f]+)$', ins['asm'].lower())

        if m:
            raw = m.group(1)
            # we've matched a breakpoint, decode the immediate
            bkpt_n = int(raw, 16 if raw.startswith('0x') else 10)

            # breakpoint 0xab indicates a semi-hosting call
            if bkpt_n == 0xAB:
                # retrieve the call type and obj registers
                # note: we would like to use `Frame.read_registers()`
                #       for this, but its only available on gdb 7.8 or
                #       newer
                r0 = gdb.parse_and_eval('$r0')
                r1 = gdb.parse_and_eval('$r1')

                call_type = int(r0)
                arg_addr = int(r1)

                if call_type == 0x05:
                    cls.handle_write(inf, arg_addr)
                else:
                    raise NotImplementedError(
                        'Call type 0x{:X} not implemented'
                        .format(call_type))

    @classmethod
    def handle_write(cls, inf, args_addr):
        # argument struct has three u32 entries: fd, address, len
        buf = inf.read_memory(args_addr, 12)

        fd, addr, l = struct.unpack('<lll', buf)

        # limit length to 4M to avoid funky behavior
        l = min(l, 4 * 1024 * 1024)

        # sanity check file descriptor
        if fd not in cls.SANE_FDS:
            raise ValueError(
                'Refusing to write to file descriptor {}'
                ' (not in {})'.format(fd, cls.SANE_FDS))

        # read the memory
        data = bytes(inf.read_memory(addr, l))

        # we manually map FDs. encoding is fixed at the rust-native utf8
        if fd == 1:
            sys.stdout.write(data.decode('utf8'))
        elif fd == 2:
            sys.stderr.write(data.decode('utf8'))

        if cls.CONTINUE:
            gdb.execute('continue')
```

Now it is time to load it and test it in gdb:

```
(gdb) source semihosting.py
(gdb) continue
Continuing.

Program received signal SIGTRAP, Trace/breakpoint trap.
0x080102e4 in hello_embed_rs::_rust_start::hfb6a6b3dc95a15dd ()
(gdb) pi SemiHostHelper.on_break()
Hello from Rust.
```

### Setting up hooks

Once the script runs correctly, we can write a start-up script for the project to make the script automatically run on each breakpoint:

```
source semihosting.py
catch signal SIGTRAP

commands
pi SemiHostHelper.on_break()
end
```

The `catch signal SIGTRAP` creates a *catchpoint*. A catchpoint functions like a breakpoint but triggers on signals instead, like the `SIGTRAP` caused by the CPU breakpoint. The following `commands` section defines the commands to be executed whenever the catchpoint triggers.

After passing the start-up script to gdb  on start using the `-x` option, gdb will automatically handle the semi-hosting breakpoints and continue execution thereafter.


Concluding remarks
------------------

Semi-hosting is another alternative to other IO methods that does not require any hardware except the likely already present debugging port. It is quite slow in comparison though and completely halts execution, so it is not suitable for high-volume or production logging. Another drawback is that if the breakpoints are not handled, execution will simply stay paused. It can, however, be invaluable when debugging the IO facilities themselves.

This article showed how one of the original semi-hosting functions defined by the ARM compiler collection can be implemented, but there is no hard rule declaring these the only possible conventions. When not going for compatibility with other systems, creating smaller and safer alternatives with restricted functionality may be a viable option as well.

<hr>

(Updated on Oct 19th, 2016):

Bonus: OpenOCD
--------------


Pointed out by [ctz99](https://www.reddit.com/user/ctz99), [OpenOCD](http://openocd.org/) supports arm semi-hosting as well, which saves the trouble of having to implement the Python scripts for gdb. Activation is easy from within gdb, when debugging through OpenOCD:

```
(gdb) monitor arm semihosting enable
semihosting is enabled
(gdb) continue
Continuing.
```

Note that gdb will then no longer receive SIGTRAPs caused by semi-hosting calls; OpenOCD will handle them itself. As a consequence, all output will be displayed by OpenOCD instead as well.
