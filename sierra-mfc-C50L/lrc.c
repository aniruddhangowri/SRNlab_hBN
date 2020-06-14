
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    unsigned char lrc;
    
    unsigned char *str = "!Setr10.0";

    int i, j;

    for (i=0; i<strlen(str); i++) {
        lrc += (unsigned char) str[i];
    }

    printf("%x\n", lrc);
    if (lrc > 256) { lrc -= (unsigned char)(256 * (int)(lrc/256)); }
    printf("%x\n", lrc);

    lrc = (unsigned char)(~lrc);
    lrc += 1;
    
    if (lrc > 256) { lrc -= (unsigned char)(256 * (int)(lrc/256)); }

    printf("%x\n", lrc);

    return 0;
}




