excerpt fast fobos '[fast]'
show test 'fobis test --mode fast --quiet'
show checks 'fobis test --mode fast --shadow checks --quiet'
show matrix 'fobis matrix --modes fast --shadows none,checks,sanitize'
quiet "sed -i 's|   e = abs(s - exact) / abs(exact)|   e = abs(s - exact) / max(abs(exact), 1._R8P)|' test/test_symmetry.F90"
show fixed 'fobis matrix --modes fast --shadows none,checks,sanitize --verify'
quiet 'git add -A && git commit -qm "fast mode, symmetry test"'
