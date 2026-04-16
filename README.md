# ⚖️ Simulador de Impacto — Reforma da Escala 6×1 no Brasil

Ferramenta de análise econométrica interativa para simular os impactos da transição da escala de trabalho 6×1 para modelos alternativos (5×2 e 4×3) no mercado de trabalho brasileiro.

## Funcionalidades

- **3 cenários** (Conservador, Moderado, Transformador) com parâmetros ajustáveis
- **Simulação Monte Carlo** (até 50.000 iterações) com intervalos de confiança 80%
- **Análise setorial** — 8 setores econômicos com índice de vulnerabilidade
- **Análise regional** — 5 regiões + mapa de vulnerabilidade por estado
- **Calculadora PME** — estima custo adicional mensal para qualquer perfil de empresa
- **Comparações internacionais** — França, Islândia, Japão, Dinamarca, Alemanha
- **Framework de perguntas guiadas** — 6 questões-chave com respostas baseadas nos modelos

## Deploy em 3 passos

### 1. Crie o repositório no GitHub

```bash
git init
git add .
git commit -m "feat: simulador reforma 6x1 v1.0"
git remote add origin https://github.com/SEU_USUARIO/reforma-6x1-simulator.git
git push -u origin main
```

### 2. Deploy no Streamlit Cloud (gratuito)

1. Acesse [share.streamlit.io](https://share.streamlit.io)
2. Conecte sua conta GitHub
3. Clique em **"New app"**
4. Selecione o repositório `reforma-6x1-simulator`
5. Entry point: `app.py`
6. Clique em **"Deploy"** — em ~2 minutos o app estará online

### 3. Compartilhe a URL pública

O Streamlit Cloud gera uma URL no formato:
```
https://SEU_USUARIO-reforma-6x1-simulator-app-XXXXX.streamlit.app
```

## Execução local

```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/reforma-6x1-simulator.git
cd reforma-6x1-simulator

# Instale as dependências
pip install -r requirements.txt

# Execute o app
streamlit run app.py
```

O app abre automaticamente em `http://localhost:8501`

## Estrutura do projeto

```
reforma-6x1-simulator/
├── app.py                  ← App Streamlit principal
├── data/
│   ├── __init__.py
│   └── dados.py            ← Dados, modelos e lógica econométrica
├── requirements.txt
└── README.md
```

## Metodologia

Os modelos são baseados em:

- **PNAD Contínua** (IBGE, 2015–2023) — informalidade, horas trabalhadas, renda por setor
- **RAIS / CAGED** (MTE, 2015–2023) — emprego formal por setor e região
- **Literatura empírica** — elasticidade custo-emprego para o Brasil (-0,15 a -0,40)
- **Evidências internacionais** — OCDE, ILO, estudos sobre França (35h), Islândia (4 dias), Japão, Dinamarca

### Modelo Monte Carlo

- **Custo laboral:** distribuição log-normal (captura assimetria positiva)
- **Emprego e produtividade:** distribuição normal
- **Multiplicadores setoriais e regionais** ajustam as estimativas para cada combinação de filtros
- **Intervalo de confiança:** percentis 10–90 (IC 80%)

### Hipóteses declaradas

1. Ganhos de produtividade levam 18–36 meses para se materializar
2. Resposta da informalidade ao custo: defasagem de 2–4 trimestres
3. Transição linear ao longo do horizonte de cada cenário
4. Encargos totais = INSS patronal 20% + FGTS 8% + férias 1/12 + 13º 1/12

## Expansões sugeridas (v2)

- [ ] Upload de CSV com dados reais do usuário
- [ ] Integração com API do IBGE (SIDRA) para dados atualizados automaticamente
- [ ] Simulação de cenários com desoneração parcial da folha
- [ ] Exportação de relatório em PDF
- [ ] Autenticação e salvamento de cenários personalizados

## Licença

MIT — uso livre para fins analíticos, acadêmicos e de política pública.

---

*Desenvolvido para fins analíticos e educacionais. Os modelos são simplificações da realidade econômica e não constituem aconselhamento de política pública formal.*
