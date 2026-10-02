#!/usr/bin/env bash
set -uo pipefail

echo "================================================================"
echo " ATLAS B2G - CAÇADOR DE MÁQUINAS ALWAYS FREE (ORACLE CLOUD)"
echo " Tentando da melhor (ARM 24GB) até a pior (AMD 1GB)..."
echo "================================================================"

COMP="${OCI_TENANCY:-$(oci iam availability-domain list --query 'data[0]."compartment-id"' --raw-output)}"
NAME="atlas-coletor"
BOOTGB=100

echo ">> Buscando imagens do Ubuntu 22.04..."
AD=$(oci iam availability-domain list --query 'data[0].name' --raw-output)
IMG_ARM=$(oci compute image list -c "$COMP" --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape "VM.Standard.A1.Flex" --sort-by TIMECREATED --query 'data[0].id' --raw-output)
IMG_AMD=$(oci compute image list -c "$COMP" --operating-system "Canonical Ubuntu" --operating-system-version "22.04" --shape "VM.Standard.E2.1.Micro" --sort-by TIMECREATED --query 'data[0].id' --raw-output)

# Configura a Rede (cria se não existir)
SUBNET=$(oci network subnet list -c "$COMP" --query 'data[0].id' --raw-output 2>/dev/null || true)
if [ -z "${SUBNET:-}" ] || [ "$SUBNET" = "null" ]; then
  echo ">> Criando rede (VCN + IGW + subnet publica)..."
  VCN=$(oci network vcn create -c "$COMP" --cidr-blocks '["10.0.0.0/16"]' --display-name vcn-atlas --dns-label vcnatlas --wait-for-state AVAILABLE --query 'data.id' --raw-output)
  IGW=$(oci network internet-gateway create -c "$COMP" --vcn-id "$VCN" --is-enabled true --display-name igw-atlas --wait-for-state AVAILABLE --query 'data.id' --raw-output)
  RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
  oci network route-table update --rt-id "$RT" --force --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
  SUBNET=$(oci network subnet create -c "$COMP" --vcn-id "$VCN" --cidr-block "10.0.0.0/24" --display-name subnet-atlas-pub --wait-for-state AVAILABLE --query 'data.id' --raw-output)
fi

[ -f "$HOME/atlas_key" ] || ssh-keygen -t rsa -b 2048 -f "$HOME/atlas_key" -N "" -q
PUBKEY=$(cat "$HOME/atlas_key.pub")
echo ">> Configurações prontas. Iniciando tentativas de criação..."
echo ""

try_launch() {
  local shape=$1; local ocpus=$2; local mem=$3; local img=$4; local nome_amigavel=$5
  
  echo ">>> TENTATIVA: $nome_amigavel"
  if [ "$shape" = "VM.Standard.E2.1.Micro" ]; then
    oci compute instance launch -c "$COMP" --availability-domain "$AD" --shape "$shape" --image-id "$img" --subnet-id "$SUBNET" --assign-public-ip true --boot-volume-size-in-gbs "$BOOTGB" --display-name "$NAME" --metadata "{\"ssh_authorized_keys\": \"$PUBKEY\"}" --wait-for-state RUNNING 1>/tmp/ok 2>/tmp/err
  else
    oci compute instance launch -c "$COMP" --availability-domain "$AD" --shape "$shape" --shape-config "{\"ocpus\": $ocpus, \"memoryInGBs\": $mem}" --image-id "$img" --subnet-id "$SUBNET" --assign-public-ip true --boot-volume-size-in-gbs "$BOOTGB" --display-name "$NAME" --metadata "{\"ssh_authorized_keys\": \"$PUBKEY\"}" --wait-for-state RUNNING 1>/tmp/ok 2>/tmp/err
  fi
  
  if [ $? -eq 0 ]; then
    echo "    [✔ SUCESSO] Máquina $nome_amigavel criada com sucesso!"
    return 0
  else
    if grep -qiE "capacity" /tmp/err; then
      echo "    [❌ FALHOU] Sem capacidade na região. Indo para a próxima opção..."
      return 1
    else
      echo "    [ERRO DESCONHECIDO]:"; cat /tmp/err; exit 1
    fi
  fi
}

# ESCADINHA DE TENTATIVAS (Do melhor para o pior)
if try_launch "VM.Standard.A1.Flex" 4 24 "$IMG_ARM" "ARM (4 Núcleos / 24GB RAM)"; then
  echo ""
elif try_launch "VM.Standard.A1.Flex" 2 12 "$IMG_ARM" "ARM (2 Núcleos / 12GB RAM)"; then
  echo ""
elif try_launch "VM.Standard.A1.Flex" 1 6 "$IMG_ARM" "ARM (1 Núcleo / 6GB RAM)"; then
  echo ""
elif try_launch "VM.Standard.E2.1.Micro" 0 1 "$IMG_AMD" "AMD Micro (1GB RAM)"; then
  echo ""
else
  echo "Todas as opções gratuitas estão esgotadas no momento. Tente novamente mais tarde."
  exit 1
fi

INSTID=$(oci compute instance list -c "$COMP" --display-name "$NAME" --lifecycle-state RUNNING --query 'data[0].id' --raw-output)
IP=$(oci compute instance list-vnics --instance-id "$INSTID" --query 'data[0]."public-ip"' --raw-output)

echo "============================================"
echo " MÁQUINA NO AR! IP: $IP"
echo " Comando de acesso: ssh -i ~/atlas_key ubuntu@$IP"
echo "============================================"
