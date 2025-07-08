# Demo

This demo shows how to run a secure genomic analysis across N independent computers, where:
- 1 computer acts as the researcher who will analyze the data
- N-1 computers are data owners who provide genomic data

## Setup on All Computers
On each computer, first install SecureGenomics:
```bash
git clone https://github.com/securegenomics/securegenomics.git && cd securegenomics && bash setup.sh
```
Then, create an account:
```bash
securegenomics register
```

## Researcher's Computer
```bash
securegenomics create # will give a <project-id>
securegenomics keygen <project-id>
```

## Data Owners' Computers
Computer 1:
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C01.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C01.annotated.nh2.variants.vcf.gz

securegenomics upload <project-id> ~/data/genome/LP6005441-DNA_C01.annotated.nh2.variants.vcf
```
Computer 2:
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C02.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C02.annotated.nh2.variants.vcf.gz

securegenomics upload <project-id> ~/data/genome/LP6005441-DNA_C02.annotated.nh2.variants.vcf
```
Computer 3:
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C03.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C03.annotated.nh2.variants.vcf.gz

securegenomics upload <project-id> ~/data/genome/LP6005441-DNA_C03.annotated.nh2.variants.vcf
```
Computer 4:
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C05.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C05.annotated.nh2.variants.vcf.gz

securegenomics upload <project-id> ~/data/genome/LP6005441-DNA_C05.annotated.nh2.variants.vcf
```

## Researcher's Computer Again
```bash
securegenomics view <project-id>
securegenomics run <project-id>
securegenomics status <project-id>
securegenomics result <project-id>
```


## At the end
```bash
rm -rf ~/data/genome
```