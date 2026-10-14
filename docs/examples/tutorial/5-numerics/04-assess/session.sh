quiet 'cat >> fobos <<"END"

[assess:area]
families = refinement precision rounding
refine   = n: arg 1 values 8 16 32 64 128 inverse
budget   = simpson: order >= 3.9; trapezoid: order >= 1.9
END'
excerpt section fobos '[assess:area]'
show assess 'fobis assess area'
show method 'fobis kb show numerics:assessment#refinement-family | head -n 12'
quiet 'git add -A && git commit -qm "area: assessment"'
