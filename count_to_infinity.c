#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
//by Dominic Alexander Cooper
int main(){
    FILE *p;
    p = fopen("system.txt","w");
    if (p == NULL) {
        perror("Error opening file");
        return 1;
    }
    char a[] = {'a','b','c','d','e','f','g','h','i','j','k','l','m','n','o',
    'p','q','r','s','t','u','v','w','x','y','z',' ','\n','\t','\\','\'','/','/',
    '<','>','?',':',';','@','#','~',']','[','{','}','`','|','!','"',
    '$','%','^','&','*','(',')','-','_','+','=','.','A','B','C','D','E',
    'F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W',
    'X','Y','Z','0','1','2','3','4','5','6','7','8','9'};
    long long k = sizeof(a) / sizeof(a[0]);
    printf("\n\tk = %lld", k);
    long long noc;
    printf("\n\tn= ");
    scanf("%lld", &noc);
    if(noc <= 0){
        return 1;
    }
    printf("Cells per file combinations as: %lld", noc);
    long long n = noc;
    long long row, col, cell, rdiv, id;
    id = 0;
    long long nbr_comb = pow(k, n);
    for (row=0; row < nbr_comb; row++){
        id++; fprintf(p,"\n\nF%lld\n\n", id);
        for(col=n-1; col>=0; col--){
            rdiv = pow(k, col);
            cell = (row/rdiv) % (k);
            fprintf(p,"%c", a[cell]);
        }
        printf("\n");
    }
    fclose(p);
    printf("This program was adapted by Dominic from lyst on https://www.stackoverflow.com");
    return 0;
}