/*
 * QEMU-user-only replacement for system(3).
 *
 * The original ARM service toggles modem GPIOs through many concurrent
 * system("echo ... > /sys/...") calls. qemu-user intermittently crashes while
 * cloning/execing those children from this multi-threaded process. Real DTU
 * hardware must never load this shim. The lab does not expose those GPIOs, so
 * hardware commands are successful no-ops. The two OTA parser file mutations
 * are reproduced with direct ARM Linux syscalls and therefore need no child.
 */

typedef unsigned int size_t;

#define ARM_NR_OPEN 5
#define ARM_NR_CLOSE 6
#define ARM_NR_UNLINK 10
#define O_WRONLY 1
#define O_CREAT 64
#define O_TRUNC 512

static int contains(const char *text, const char *needle)
{
    const char *start;
    const char *scan;

    if (!text || !needle || !*needle)
        return 0;
    for (start = text; *start; ++start) {
        for (scan = needle; *scan && start[scan - needle] == *scan; ++scan)
            ;
        if (!*scan)
            return 1;
    }
    return 0;
}

static long arm_syscall1(long number, const char *arg0)
{
    register long r0 __asm__("r0") = (long)arg0;
    register long r7 __asm__("r7") = number;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r7) : "memory");
    return r0;
}

static long arm_syscall3(long number, const char *arg0, long arg1, long arg2)
{
    register long r0 __asm__("r0") = (long)arg0;
    register long r1 __asm__("r1") = arg1;
    register long r2 __asm__("r2") = arg2;
    register long r7 __asm__("r7") = number;
    __asm__ volatile("svc 0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory");
    return r0;
}

static void truncate_ota_info(void)
{
    long fd = arm_syscall3(ARM_NR_OPEN, "/data/phnixIot_device_OTA_INFO",
                           O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd >= 0) {
        register long r0 __asm__("r0") = fd;
        register long r7 __asm__("r7") = ARM_NR_CLOSE;
        __asm__ volatile("svc 0" : "+r"(r0) : "r"(r7) : "memory");
    }
}

int system(const char *command)
{
    if (!command)
        return 1;
    if (contains(command, "/cache/phnixIot_device_OTA"))
        (void)arm_syscall1(ARM_NR_UNLINK, "/cache/phnixIot_device_OTA");
    if (contains(command, "/data/phnixIot_device_OTA_INFO"))
        truncate_ota_info();
    return 0;
}
