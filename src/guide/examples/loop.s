// Sum 1 + 2 + 3 + 4 + 5 with a counting loop.
        .section .text
        .global main
main:
        mov     x0, 0           // sum = 0
        mov     x1, 1           // i = 1
sumLoop:
        add     x0, x0, x1      // sum = sum + i
        add     x1, x1, 1       // i = i + 1
        cmp     x1, 5           // compare i with 5: sets N, Z, C and V
        ble     sumLoop         // repeat while i <= 5

        ret                     // return sum (15) in w0
