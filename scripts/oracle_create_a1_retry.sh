#!/usr/bin/env bash
# =====================================================================
# Cria (se preciso) a REDE pública e a VM Ampere A1 (4 OCPU / 24 GB / 100 GB),
# com RETRY automático até a capacidade do Always Free liberar.
# RODAR NO CLOUD SHELL da Oracle (a CLI já vem logada). Não precisa criar VCN
# no Console — este script cria a rede inteira sozinho.
# =====================================================================
set -uo pipefail

COMP="${OCI_TENANCY:-$(oci iam availability-domain list --query 'data[0]."compartment-id"' --raw-output)}"
SHAPE="VM.Standard.A1.Flex"; OCPUS=4; MEMGB=24; BOOTGB=100; NAME="atlas-coletor"; ESPERA=90

echo "==> Tenancy: $COMP"
AD=$(oci iam availability-domain list --query 'data[0].name' --raw-output)
IMG=$(oci compute image list -c "$COMP" --operating-system "Canonical Ubuntu" \
      --operating-system-version "22.04" --shape "$SHAPE" --sort-by TIMECREATED \
      --query 'data[0].id' --raw-output)
echo "    AD     = $AD"
echo "    Imagem = $IMG"

# ---------- REDE: usa subnet existente, senão cria VCN + IGW + rota + subnet ----------
SUBNET=$(oci network subnet list -c "$COMP" --query 'data[0].id' --raw-output 2>/dev/null || true)
if [ -z "${SUBNET:-}" ] || [ "$SUBNET" = "null" ]; then
  echo "==> Nenhuma rede encontrada — criando VCN + internet gateway + subnet publica..."
  VCN=$(oci network vcn create -c "$COMP" --cidr-blocks '["10.0.0.0/16"]' \
        --display-name vcn-atlas --dns-label vcnatlas --wait-for-state AVAILABLE \
        --query 'data.id' --raw-output)
  IGW=$(oci network internet-gateway create -c "$COMP" --vcn-id "$VCN" --is-enabled true \
        --display-name igw-atlas --wait-for-state AVAILABLE --query 'data.id' --raw-output)
  RT=$(oci network vcn get --vcn-id "$VCN" --query 'data."default-route-table-id"' --raw-output)
  oci network route-table update --rt-id "$RT" --force \
    --route-rules "[{\"destination\":\"0.0.0.0/0\",\"destinationType\":\"CIDR_BLOCK\",\"networkEntityId\":\"$IGW\"}]" >/dev/null
  SUBNET=$(oci network subnet create -c "$COMP" --vcn-id "$VCN" --cidr-block "10.0.0.0/24" \
        --display-name subnet-atlas-pub --wait-for-state AVAILABLE --query 'data.id' --raw-output)
  echo "==> Rede criada (VCN + internet + subnet publica)."
fi
echo "    Subnet = $SUBNET"

# ---------- chave SSH (fica salva no Cloud Shell) ----------
if [ ! -f "$HOME/atlas_key" ]; then
  ssh-keygen -t rsa -b 2048 -f "$HOME/atlas_key" -N "" -q
  echo "==> Chave SSH criada em ~/atlas_key"
fi
PUBKEY=$(cat "$HOME/atlas_key.pub")

# ---------- cria a VM com retry ate liberar capacidade ----------
echo "==> Criando a VM (4/24, 100GB). Retry a cada ${ESPERA}s ate liberar. Ctrl+C pra parar."
n=0
while true; do
  n=$((n+1)); echo "[$(date +%H:%M:%S)] tentativa $n..."
  if oci compute instance launch \
      -c "$COMP" --availability-domain "$AD" --shape "$SHAPE" \
      --shape-config "{\"ocpus\": $OCPUS, \"memoryInGBs\": $MEMGB}" \
      --image-id "$IMG" --subnet-id "$SUBNET" --assign-public-ip true \
      --boot-volume-size-in-gbs "$BOOTGB" --display-name "$NAME" \
      --metadata "{\"ssh_authorized_keys\": \"$PUBKEY\"}" \
      --wait-for-state RUNNING 1>/tmp/launch_ok 2>/tmp/launch_err; then
    echo "==> 🎉 VM CRIADA E RODANDO!"
    break
  fi
  if grep -qiE "out of host capacity|outofcapacity|capacity" /tmp/launch_err; then
    echo "    ainda sem capacidade — aguardando ${ESPERA}s..."
    sleep "$ESPERA"
  else
    echo "==> Erro (nao e capacidade) — veja:"; cat /tmp/launch_err; exit 1
  fi
done

INSTID=$(oci compute instance list -c "$COMP" --display-name "$NAME" --lifecycle-state RUNNING --query 'data[0].id' --raw-output)
IP=$(oci compute instance list-vnics --instance-id "$INSTID" --query 'data[0]."public-ip"' --raw-output)
echo "============================================================"
echo " VM no ar!  IP publico: $IP"
echo " Entrar:   ssh -i ~/atlas_key ubuntu@$IP"
echo "============================================================"
