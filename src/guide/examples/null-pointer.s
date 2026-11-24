// INTENTIONAL ERROR: this program loads through a null pointer.
// Address 0 is unmapped in this simulator.
        .section .text
        .global main
main:
        mov     x1, 5           // an ordinary value
        mov     x0, 0           // x0 = NULL: no memory lives at address 0
        ldr     x2, [x0]        // fails here: the load reads address 0

        mov     w0, 0           // never reached
        ret
