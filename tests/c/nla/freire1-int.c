/* Algorithm for finding the closest integer to square root,
 * more details, see : http://www.pedrofreire.com/sqrt/sqrt1.en.html 

Note: for some reason using cpa was able to disprove these
cpa.sh -kInduction -setprop solver.solver=z3 freire1.c
*/

extern void abort(void); 
void reach_error(){}
extern double __VERIFIER_nondet_double(void);
extern void abort(void); 
void assume_abort_if_not(int cond) { 
  if(!cond) {abort();}
}
void __VERIFIER_assert(int cond) {
    if (!(cond)) {
    ERROR:
        {reach_error();abort();}
    }
    return;
}

int main() {
    int r;
    int a, x;
    x = __VERIFIER_nondet_int();
    a = x * 2;
    r = 0;

    while (1) {
        __VERIFIER_assert((int)(r*r - a - r + 2*x) == 0);

        if (!(x > r))
            break;
        x = x - r;
        r = r + 1;
    }

    __VERIFIER_assert((int)(r*r - a - r + 2*x) == 0);
    return 0;
}
