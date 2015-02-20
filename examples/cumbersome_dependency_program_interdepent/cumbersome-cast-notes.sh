#!/bin/bash
echo -e "\033[1m Hi all Fortran Poor men! \033[0m" ; sleep 4
echo -e "\033[1m Let us play with FoBiS.py \033[0m" ; sleep 4
echo -e "\033[1m Let us assume our aim is build this cumbersome hello world program \033[0m" ; sleep 4
echo "tree" ; sleep 2
tree
echo -e "\033[1m  \033[0m"
echo -e "\033[1m It is very cumbersome... The main program is into src/cumbersome.f90 \033[0m" ; sleep 4
echo -e "\033[1m It depends on both the libraries into dependency_lib_1 and dependency_lib_2 \033[0m" ; sleep 4
echo -e "\033[1m If we try to build cumbersome directly we obtain... \033[0m" ; sleep 4
echo
echo -e "\033[1;31m gfortran src/cumbersome.f90 \033[0m" ; sleep 2
gfortran src/cumbersome.f90
echo
echo -e "\033[1m Obviously this does not work... \033[0m" ; sleep 4
echo -e "\033[1m We must firstly build dependency_lib_1 \033[0m" ; sleep 4
echo
echo -e "\033[1;31m gfortran dependency_lib_1/src/library.f90 \033[0m" ; sleep 2
gfortran dependency_lib_1/src/library.f90
echo
echo -e "\033[1m Oh no! This library is even more cumbersome than the program! \033[0m" ; sleep 4
echo -e "\033[1m This library has nested include/use statements \033[0m" ; sleep 4
echo -e "\033[1m Ok, We need to write a makefile... \033[0m" ; sleep 4
echo -e "\033[1m Wait! It is 2015... Do we still complain with tabs, rules, modules inter-dependencies? \033[0m" ; sleep 4
echo -e "\033[1m Do you ever write a makefile with many cumbersome Fortran 95+ module-usage-statements? \033[0m" ; sleep 4
echo -e "\033[1m It can become quickly a nightmare \033[0m" ; sleep 4
echo -e "\033[1m Give FoBiS.py a chance \033[0m" ; sleep 4
echo
echo -e "\033[1;31m FoBiS.py build \033[0m" ; sleep 2
FoBiS.py build
echo
echo -e "\033[1m Wow... What happens? \033[0m" ; sleep 4
echo -e "\033[1m + FoBiS.py builds src/cumbersome.f90, but before \033[0m" ; sleep 4
echo -e "\033[1m   - firstly build dependency_lib_1 \033[0m" ; sleep 4
echo -e "\033[1m     * this library is even more cumbersome, but FoBiS.py automatically resolves the \033[0m"
echo -e "\033[1m       dependencies hierarchy! \033[0m" ; sleep 4
echo -e "\033[1m   - secondly build dependency_lib_2 \033[0m" ; sleep 4
echo -e "\033[1m   - finally Cumbersome is built \033[0m" ; sleep 4
echo
echo -e "\033[1m Well, you are thinking that for doing such a complex building the FoBiS.py configuration \033[0m" ; sleep 1
echo -e "\033[1m file (fobos) should be complex, more and more (and more) complex than a corresponding \033[0m" ; sleep 4
echo -e "\033[1m working makefile. Definitely not! Let us see the fobos file \033[0m" ; sleep 4
echo
echo -e "\033[1;31m cat fobos \033[0m" ; sleep 2
cat fobos
echo
echo -e "\033[1m Is it simple enough? \033[0m" ; sleep 4
echo -e "\033[1m Note that is a very cumbersome scenario... In most cases, FoBiS.py can do \033[0m" ; sleep 4
echo -e "\033[1m similar stuff even without a fobos file, directly from the command line! \033[0m" ; sleep 4
echo -e "\033[1;31m Bye bye Fortran poor men \033[0m"
