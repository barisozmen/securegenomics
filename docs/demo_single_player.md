# Demo (single player mode) (~3 minutes)

This demo shows how to run a genomic analysis wholly in your local computer.

It includes everything from downloading the example genome to running the analysis and interpreting the results.

#### Install SecureGenomics
```bash
git clone https://github.com/securegenomics/securegenomics.git && cd securegenomics && bash setup.sh
```

#### Download example human genome (skip this if you'll use your own genome)
```bash
mkdir -p ~/.securegenomics/example-genome && wget -P ~/.securegenomics/example-genome https://storage.googleapis.com/genomics-public-data/simons-genome-diversity-project/vcf/LP6005441-DNA_C05.annotated.nh2.variants.vcf.gz && gunzip ~/.securegenomics/example-genome/LP6005441-DNA_C05.annotated.nh2.variants.vcf.gz
```

#### Run Alzheimer's Disease Polygenic Risk Score (PRS) analysis
```bash
secgen local analyze -p alzheimer-prs -f ~/.securegenomics/example-genome/LP6005441-DNA_C05.annotated.nh2.variants.vcf
```


#### If used example genome, you can remove it
```bash
rm -rf  ~/.securegenomics/example-genome
```