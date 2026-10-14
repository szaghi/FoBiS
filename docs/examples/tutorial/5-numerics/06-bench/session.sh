quiet 'cat >> fobos <<"END"

[case:fine]
description = sin(x) over [0, pi] with 4 million intervals, a benchmark
target      = src/area.F90
mode        = release
args        = 4000000
quantities  = stdout
tolerance   = *: ulp 4

[bench:fine]
min_runs = 10
target   = 0.02
END'
excerpt bench fobos '[bench:fine]'
measure compare 'fobis bench fine --compare HEAD~1 2>/dev/null'
measure record 'fobis bench fine --record 2>/dev/null'
show history 'wc -l verification/bench/fine.jsonl'
quiet 'git add -A && git commit -qm "fine: a benchmark"'
