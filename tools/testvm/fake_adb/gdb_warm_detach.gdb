set architecture arm
set pagination off
set confirm off
target remote 127.0.0.1:12345
printf "FOXAIR_WARM_DETACHED\n"
detach
quit
