#include <stdint.h>
//#include <smmintrin.h>
//#include <cpuid.h>
#define bit_SSE4_2 (1<<20)
#ifndef CPUIDEMU

#if defined(__APPLE__) && defined(__i386__)
void cpuid(uint32_t op, uint32_t *eax, uint32_t *ebx, uint32_t *ecx, uint32_t *edx);
#else
static inline void cpuid(uint32_t op, uint32_t *eax, uint32_t *ebx, uint32_t *ecx, uint32_t *edx){
  __asm__ __volatile__
    ("cpuid": "=a" (*eax), "=b" (*ebx), "=c" (*ecx), "=d" (*edx) : "a" (op) : "cc");

}
#endif

#else

typedef struct {
  uint32_t id, a, b, c, d;
} idlist_t;

typedef struct {
  char *vendor;
  char *name;
  uint32_t start, stop;
} vendor_t;

extern idlist_t idlist[];
extern vendor_t vendor[];

static uint32_t cv = VENDOR;

void cpuid(uint32_t op, uint32_t *eax, uint32_t *ebx, uint32_t *ecx, uint32_t *edx){

  static uint32_t current = 0;

  uint32_t start = vendor[cv].start;
  uint32_t stop  = vendor[cv].stop;
  uint32_t count = stop - start;

  if ((current < start) || (current > stop)) current = start;

  while ((count > 0) && (idlist[current].id != op)) {

    current ++;
    if (current > stop) current = start;
    count --;

  }

  *eax = idlist[current].a;
  *ebx = idlist[current].b;
  *ecx = idlist[current].c;
  *edx = idlist[current].d;
}

#endif

int is_initialized=0;
uint32_t slowcrc_table[1<<8];

void slowcrc_init() {
	uint32_t i, j, a;

	for (i=0;i<(1<<8);i++) {
		a=((uint32_t)i)<<24;
		for (j=0;j<8;j++) {
			if (a&0x80000000)
				a=(a<<1)^0x11EDC6F41;
			else
				a=(a<<1);
		}
		slowcrc_table[i]=a;
	}
	is_initialized=1;
}

uint32_t slowcrc(char *str, uint32_t len) {
	uint32_t lcrc=~0;
	char *p, *e;

	e=str+len;
	for (p=str;p < e;++p)
		lcrc=(lcrc>>8)^slowcrc_table[(lcrc^(*p))&0xff];
	return ~lcrc;
}

uint32_t fastcrc(const char *str, uint32_t len) {
	uint32_t q=len/sizeof(uint32_t),
		     r=len%sizeof(uint32_t),
		     *p=(uint32_t*)str,
		     crc=0;

	while (q--) {
//		crc = _mm_crc32_u32(crc,*p);
		__asm__ __volatile__(
				".byte 0xf2, 0xf, 0x38, 0xf1, 0xf1;"
				:"=S"(crc)
				:"0"(crc), "c"(*p)
				);
		p++;
	}

	str=(char*)p;
	while (r--) {
//		crc = _mm_crc32_u8(crc,*str);
		__asm__ __volatile__(
				".byte 0xf2, 0xf, 0x38, 0xf0, 0xf1"
				:"=S"(crc)
				:"0"(crc), "c"(*str)
		);
		str++;
	}

	return crc;
}

uint32_t crc32(char *str, uint32_t len) {
  uint32_t eax, ebx, ecx, edx;
  cpuid(1, &eax, &ebx, &ecx, &edx);

  if (ecx & bit_SSE4_2){
	    return fastcrc(str,len);
  	 }else{
  		 if (!is_initialized){
  			slowcrc_init();
  		 }
  		 return slowcrc(str,len);
  	 }
}
