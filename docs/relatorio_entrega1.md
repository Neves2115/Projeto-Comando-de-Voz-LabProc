% Central de comandos por voz para o kit Freenove
% Entrega 1 - Semana inicial
% 2026

# 1. Introdução

Este projeto propõe uma central de comandos por voz executada em Raspberry Pi 3 com periféricos do kit Freenove. A ideia é criar uma solução simples, demonstrável e útil, capaz de reconhecer comandos curtos e acionar LEDs, servomotor, LCD, matriz de LEDs e sensor de distância.

# 2. Motivação

Assistentes de voz em nuvem nem sempre são adequados para um projeto acadêmico com hardware embarcado. A dependência de internet, de APIs externas e de modelos grandes pode tornar a demonstração menos confiável. Por isso, o foco aqui é uma solução local, com comandos fechados e resposta rápida.

O projeto é interessante porque une três aspectos importantes:

- processamento de áudio e reconhecimento de fala;
- uso de sensores e atuadores em Raspberry Pi;
- feedback visual e físico para facilitar a demonstração.

# 3. Objetivo geral

Desenvolver uma central local de comandos por voz para o kit Freenove, rodando em Raspberry Pi 3, capaz de interpretar frases simples e executar ações no hardware com retorno imediato ao usuário.

# 4. Requisitos

## Requisitos funcionais

- Capturar áudio por microfone.
- Reconhecer comandos de voz curtos em português.
- Executar ações associadas aos comandos reconhecidos.
- Exibir o estado do sistema no LCD.
- Acionar LEDs e servomotor.
- Ler o sensor de distância quando solicitado.
- Registrar eventos em arquivo local ou SQLite.
- Permitir um modo manual por botões ou teclado.

## Requisitos não funcionais

- Rodar em Raspberry Pi 3.
- Usar processamento local sempre que possível.
- Manter o sistema leve e fácil de demonstrar.
- Ter estrutura modular em Python.
- Ser legível e simples de manter.

# 5. Escopo do MVP

## Dentro do escopo

- 5 a 8 comandos fixos.
- Ligação e desligamento de LEDs.
- Movimentação do servo para posições pré-definidas.
- Exibição de mensagens no LCD.
- Consulta do sensor de distância.

## Fora do escopo inicial

- Conversa aberta com IA grande.
- Reconhecimento de múltiplos falantes em tempo real.
- Integrações externas obrigatórias.
- Reconhecimento contínuo de fala sem pausas.

# 6. Arquitetura proposta

```text
Microfone
   |
   v
Captura de áudio
   |
   v
Reconhecimento de fala offline
   |
   v
Interpretador de comandos
   |
   +--> GPIO -> LEDs
   +--> PWM  -> Servomotor
   +--> I2C   -> LCD
   +--> Leitura -> Sensor de distância
   +--> Log local -> Arquivo / SQLite
```

A arquitetura foi pensada para ser modular. Cada bloco pode ser testado separadamente, o que reduz o risco de falha e facilita a depuração.

# 7. Caminho de implementação

A implementação será feita em etapas:

1. Validar microfone e captura de áudio.
2. Testar reconhecimento de fala com comandos curtos.
3. Integrar LEDs e servomotor.
4. Conectar o LCD como feedback principal.
5. Incluir sensor de distância e logs locais.
6. Refinar a experiência da demonstração.

# 8. Primeira release

A release v0.1.0 contém a organização inicial do projeto, a documentação de base e a proposta técnica refinada. Nesta fase, o objetivo é estabelecer a fundação para a implementação prática nas próximas semanas.

# 9. Conclusão

A solução proposta atende ao objetivo de ser simples, demonstrável e claramente vinculada ao uso do Raspberry Pi 3. A combinação de voz, sensores e atuadores permite uma apresentação convincente, com possibilidade de evolução para recursos de edge AI sem extrapolar o escopo do projeto.
