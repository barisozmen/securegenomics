# Demo (multi-player mode) (~10 minutes)

This demo shows how to run a homomorphic encryption-based genomic analysis across N independent computers, where:
- 1 computer acts as the researcher who will analyze the data
- N-1 computers are data owners who provide genomes


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
secgen create # will give a <project-id> and automatically generate a key pair and upload its public part to the server
```

## Data Owners' Computers
#### Computer 1

1. download an example genome
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C01.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C01.annotated.nh2.variants.vcf.gz
```
2. create an account
```bash
secgen login --email=dataowner1@gmail.com --password=dataowner1@gmail.com
```
3. upload the genome
```bash
secgen upload 17cf92b8-0cc3-433f-8690-cc672192e510 ~/data/genome/LP6005441-DNA_C01.annotated.nh2.variants.vcf
```
#### Computer 2

1. download an example genome
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C02.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C02.annotated.nh2.variants.vcf.gz
```
2. create an account
```bash
secgen login --email=dataowner2@gmail.com --password=dataowner2@gmail.com
```
3. upload the genome
```bash
secgen upload 17cf92b8-0cc3-433f-8690-cc672192e510 ~/data/genome/LP6005441-DNA_C02.annotated.nh2.variants.vcf
```
#### Computer 3

1. download an example genome
```bash
mkdir -p ~/data/genome && wget -P ~/data/genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C03.annotated.nh2.variants.vcf.gz && gunzip ~/data/genome/LP6005441-DNA_C03.annotated.nh2.variants.vcf.gz
```
2. create an account
```bash
secgen login --email=dataowner3@gmail.com --password=dataowner3@gmail.com
```
3. upload the genome
```bash
secgen upload 17cf92b8-0cc3-433f-8690-cc672192e510 ~/data/genome/LP6005441-DNA_C03.annotated.nh2.variants.vcf
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
