// Allocate two longs on the heap, fill them, then free them.
        .section .text
        .equ    MAIN_STACK_BYTECOUNT, 16
        .equ    LPOINTER, 8     // where main keeps the pointer
        .global main
main:
        sub     sp, sp, MAIN_STACK_BYTECOUNT
        str     x30, [sp]

        mov     x0, 16          // malloc(16): room for two longs
        bl      malloc          // x0 = address of the new block
        str     x0, [sp, LPOINTER]

        mov     x1, 42
        str     x1, [x0]        // p[0] = 42
        mov     x1, 7
        str     x1, [x0, 8]     // p[1] = 7

        ldr     x0, [sp, LPOINTER]
        bl      free            // free(p): the block disappears from the heap

        ldr     x30, [sp]
        add     sp, sp, MAIN_STACK_BYTECOUNT
        mov     w0, 0           // return 0
        ret
