public class PLDI09_Fig4_4 {
    public static void vtrace1(int n, int m, int t, int h){}
    public static void main (String[] args) {
    }

    public static int mainQ(int n, int m){
	assert (m>0);
	assert (n>0);

	int i = n;
	int t = 0;
	int h = n/m;
     
	/* int h = 0; */
	/* while(m*h<=n){ */
	/* 	  h++; */
	/* } */
	/* h--; */
	while(i>0){
	    if (i < m) {
		i--;
	    }else{
		i = i-m;
	    }
	    t++;
	}
     
	vtrace1(n, m, t, h);
     
	//dig2: l26: -c2 <= -1, c2*m - c2 - n + t == 0, c1 - m <= -1, -t <= -2, c1 + c2 - t == 0, c2 - t <= 0

	//Note: I got the above results which I think are right. But I have to manually pass in the flag -maxdeg 3  (i.e., DIG attempts to use maxdeg 4 automatically, but this requires many traces that it wasn't able to get).
     
     
	return 0;
    }
}
