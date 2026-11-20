// Read a line with fgets, then print it back with printf.
        .section .rodata
promptStr:
        .string "What is your name? "
greetingStr:
        .string "Hello, %s!\n"

        .section .bss
name:   .skip   32              // char name[32]

        .section .text
        .equ    NAME_LENGTH, 32
        .equ    MAIN_STACK_BYTECOUNT, 16
        .global main
main:
        sub     sp, sp, MAIN_STACK_BYTECOUNT
        str     x30, [sp]

        adr     x0, promptStr
        bl      printf          // printf("What is your name? ")

        adr     x0, name
        mov     x1, NAME_LENGTH
        mov     x2, 0           // the stream: 0 means the simulator's stdin
        bl      fgets           // fgets(name, 32, stdin): the input box opens

        adr     x0, greetingStr
        adr     x1, name
        bl      printf          // printf("Hello, %s!\n", name)

        ldr     x30, [sp]
        add     sp, sp, MAIN_STACK_BYTECOUNT
        mov     w0, 0           // return 0
        ret
