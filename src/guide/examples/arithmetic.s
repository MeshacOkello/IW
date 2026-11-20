// Arithmetic: watch values move through registers.
        .section .text
        .global main
main:
        mov     x1, 20          // x1 = 20
        mov     x2, 5           // x2 = 5
        add     x3, x1, x2      // x3 = x1 + x2 = 25
        sub     x4, x1, x2      // x4 = x1 - x2 = 15
        mul     x5, x3, x2      // x5 = x3 * x2 = 125

        mov     w0, 0           // return 0
        ret
