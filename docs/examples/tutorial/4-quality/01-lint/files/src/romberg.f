C     ROMBERG INTEGRATION: TRAPEZOID ESTIMATES WITH 1, 2, 4, ... STEPS,
C     EXTRAPOLATED UNTIL TWO DIAGONAL VALUES AGREE WITHIN TOL.
      DOUBLE PRECISION FUNCTION ROMB(F, A, B, TOL)
      DOUBLE PRECISION F, A, B, TOL
      EXTERNAL F
      DOUBLE PRECISION R(10,10), H, S
      INTEGER I, J, K, N
      H = B - A
      R(1,1) = 0.5D0*H*(F(A)+F(B))
      N = 1
      DO 30 I = 2, 10
         H = 0.5D0*H
         S = 0.0D0
         DO 10 K = 1, N
            S = S + F(A+DBLE(2*K-1)*H)
   10    CONTINUE
         R(I,1) = 0.5D0*R(I-1,1) + H*S
         N = 2*N
         DO 20 J = 2, I
            R(I,J) = R(I,J-1)
     &             + (R(I,J-1)-R(I-1,J-1))/(4.0D0**(J-1)-1.0D0)
   20    CONTINUE
         IF (DABS(R(I,I)-R(I-1,I-1)) .LT. TOL) GOTO 40
   30 CONTINUE
      I = 10
   40 ROMB = R(I,I)
      RETURN
      END
