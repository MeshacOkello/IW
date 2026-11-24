// Walk an array in .data with a pointer and store the total.
        .section .data
array:  .quad   3, 1, 4, 1      // four 8-byte longs
total:  .quad   0               // written at the end

        .section .text
        .global main
main:
        adr     x1, array       // x1 points at array[0]
        mov     x2, 4           // elements left to add
        mov     x0, 0           // sum = 0
sumLoop:
        ldr     x3, [x1], 8     // x3 = *x1, then move x1 to the next long
        add     x0, x0, x3      // sum = sum + x3
        sub     x2, x2, 1       // one fewer element left
        cbnz    x2, sumLoop     // repeat until none are left

        adr     x4, total
        str     x0, [x4]        // total = 9

        mov     w0, 0           // return 0
        ret
