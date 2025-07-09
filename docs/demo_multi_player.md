# Demo, Multi-Player Mode (~10 MINUTES)

This demo shows how to run a secure genomic analysis across N independent computers, where:
- 1 computer acts as the researcher who will analyze the data
- N-1 computers are data owners who provide genomic data

Follow this 10-minute guide to try a complete proof-of-concept workflow using example genomes.

## Setup on All Computers
On each computer, first install SecureGenomics:
```bash
git clone https://github.com/securegenomics/securegenomics.git && cd securegenomics && bash setup.sh
```
Then, create an account:
```bash
secgen register
```

## Researcher's Computer
```bash
secgen create # will give a <project-id>
```
```bash
secgen keygen <project-id>
```

## Data Owners' Computers
Computer 1:
do in order
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C01.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C01.annotated.nh2.variants.vcf.gz
```
```bash
secgen register --email=dataowner1@gmail.com --password=dataowner1@gmail.com
```
```bash
secgen upload <project-id> ~/data/genome/LP6005441-DNA_C01.annotated.nh2.variants.vcf
```
Computer 2:
do in order
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C02.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C02.annotated.nh2.variants.vcf.gz
```
```bash
secgen register --email=dataowner2@gmail.com --password=dataowner2@gmail.com
```
```bash
secgen upload <project-id> ~/data/genome/LP6005441-DNA_C02.annotated.nh2.variants.vcf
```
Computer 3:
do in order
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C03.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C03.annotated.nh2.variants.vcf.gz

secgen register --email=dataowner3@gmail.com --password=dataowner3@gmail.com

secgen upload <project-id> ~/data/genome/LP6005441-DNA_C03.annotated.nh2.variants.vcf
```
Computer 4:
do in order
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C05.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C05.annotated.nh2.variants.vcf.gz
```
```bash
secgen register --email=dataowner4@gmail.com --password=dataowner4@gmail.com
```
```bash
secgen upload <project-id> ~/data/genome/LP6005441-DNA_C05.annotated.nh2.variants.vcf
```

## Researcher's Computer Again
```bash
secgen view <project-id>
secgen run <project-id>
secgen status <project-id>
secgen result <project-id>
```


## At the end
```bash
rm -rf ~/data/genome
```