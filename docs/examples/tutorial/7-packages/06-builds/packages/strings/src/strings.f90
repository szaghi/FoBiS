module strings
!< Case conversion of strings.
implicit none
private
public :: upper
contains
   pure function upper(text) result(up)
   !< The text in upper case.
   character(*), intent(in) :: text !< Text.
   character(len(text))     :: up   !< Upper case.
   integer                  :: i    !< Counter.
   up = text
   do i = 1, len(text)
      if (text(i:i) >= 'a' .and. text(i:i) <= 'z') up(i:i) = achar(iachar(text(i:i)) - 32)
   enddo
   endfunction upper
end module strings
