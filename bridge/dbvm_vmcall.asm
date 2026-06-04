.code

PUBLIC smem_vmcall_intel
PUBLIC smem_vmcall_amd

; Windows x64:
; rcx = vmcallinfo
; rdx = password1
; r8  = password3
; r9  = out_rdx

smem_vmcall_intel PROC
    push rbx
    mov r10, r9
    mov rax, rcx
    mov rcx, r8
    ; rdx already contains password1
    vmcall
    test r10, r10
    jz done_intel
    mov [r10], rdx
done_intel:
    pop rbx
    ret
smem_vmcall_intel ENDP

smem_vmcall_amd PROC
    push rbx
    mov r10, r9
    mov rax, rcx
    mov rcx, r8
    ; rdx already contains password1
    vmmcall
    test r10, r10
    jz done_amd
    mov [r10], rdx
done_amd:
    pop rbx
    ret
smem_vmcall_amd ENDP

END
