measure gprof 'fobis profile fine 2>/dev/null'
needs valgrind
measure callgrind 'fobis profile fine --tool callgrind --top 6 2>/dev/null'
