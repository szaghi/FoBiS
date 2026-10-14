source ./env.sh
show check 'fobis ecosystem check core'
quiet 'sed -i "s/twice/double/g" core/src/core_m.f90 core/src/test_core.f90'
show diff 'git -C core diff --stat'
show impact 'fobis ecosystem impact core'
show broken 'fobis ecosystem check core'
quiet 'git -C core checkout -- .'
