set architecture arm
set pagination off
set confirm off
set print thread-events off
handle SIGILL nostop noprint pass
handle SIGFPE nostop noprint nopass
target remote 127.0.0.1:12345
hbreak *0x1fe40
condition 1 *(unsigned int *)0x930dc == 0 && *(unsigned char *)0x98a94 == 12
continue
printf "FOXAIR_OTA_YIELD pc=%p uart=%u step=%u\n", $pc, *(unsigned int *)0x930dc, *(unsigned char *)0x98a94
if $pc != 0x1fe40
  printf "FOXAIR_OTA_PRECONDITION_REJECTED\n"
  detach
  quit
end
disable 1
# This parser-return stop is one-shot.  Explicitly disabling a persistent
# breakpoint after it fired races with QEMU's multi-thread remote target: on a
# busy first run GDB can already regard another thread as running and reject
# the explicit disable command, aborting the batch before C350.  A temporary hardware breakpoint
# is removed by GDB as part of the stop event and needs no follow-up command.
thbreak *0x1c4bc
commands 2
  silent
  printf "FOXAIR_OTA_POST_PARSER pc=%p\n", $pc
  continue
end
hbreak *0x1ba04
commands 3
  silent
  printf "FOXAIR_OTA_C36E ssid=0x%x status=%u\n", *(unsigned char *)($r0+1), *(unsigned char *)($r0+3)
  detach
  quit
end
set $return_pc = $pc
set {char[232]} 0x94ab4 = "{\"cmd\":\"CMD_OTA\",\"code\":\"0033\",\"param\":{\"softwareCode\":\"82400644\",\"softwareVer\":\"V3.3\",\"ssid\":\"0063\",\"fileMD5\":\"CEB6A4BF386FF644E23E410023E74673\",\"fileSize\":287598,\"otaFileDownloadAddr\":\"http://127.0.0.1:8081/phnixIot_device_OTA\"}}"
printf "FOXAIR_OTA_INJECT_0033\n"
set $r0 = 0x94ab4
set $lr = $return_pc
set $pc = 0x19958
continue
