# apps/core/services/deepseek_service.py

import requests
import json
from typing import List, Dict, Any, Optional

from django.conf import settings
from apps.learning.models import Topic
from apps.scheduling.models import StudyPlan

# --- Configuração Central da API ---

# URL da API do DeepSeek para o modelo de chat
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

# Headers padrão para todas as requisições
# A chave de API é lida das configurações do Django (que a lê do .env )
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}"
}

# --- Função Auxiliar Genérica para Chamadas à API ---

def _call_deepseek_api(prompt: str, is_json_output: bool = False) -> Dict[str, Any]:
    """
    Função auxiliar que lida com a chamada real para a API do DeepSeek.
    Centraliza a lógica de requisição e tratamento de erros básicos.
    """
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Você é um assistente especialista e prestativo."},
            {"role": "user", "content": prompt}
        ]
    }
    # Se esperamos um JSON, instruímos o modelo a usar o modo JSON
    if is_json_output:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=HEADERS, json=payload, timeout=90)
        
        # Levanta um erro para respostas mal-sucedidas (ex: 401, 404, 500)
        response.raise_for_status()
        
        return response.json()

    except requests.exceptions.RequestException as e:
        # Lida com erros de rede, timeout, etc.
        print(f"Erro na chamada da API DeepSeek: {e}")
        # Em um projeto real, aqui teríamos um log mais robusto
        raise ConnectionError(f"Falha ao se comunicar com a API do DeepSeek: {e}") from e
    except json.JSONDecodeError as e:
        # Lida com casos onde a resposta da API não é um JSON válido
        print(f"Erro ao decodificar a resposta JSON da API: {e}")
        raise ValueError(f"A resposta da API não era um JSON válido: {e}") from e


# --- Implementação dos Serviços Específicos ---

def sugerir_plano_de_topico(titulo_disciplina: str, titulo_topico: str) -> str:
    """
    Gera um plano de estudo detalhado para um tópico de uma disciplina.
    """
    prompt = (
        f"Aja como um tutor universitário. Para a disciplina de '{titulo_disciplina}', "
        f"crie um plano de estudos em formato Markdown para o tópico '{titulo_topico}'. "
        "Descreva os conceitos fundamentais, os pré-requisitos e sugira uma ordem de estudo com os principais pontos."
    )
    
    try:
        api_response = _call_deepseek_api(prompt)
        # Extrai o conteúdo da resposta do modelo
        content = api_response['choices'][0]['message']['content']
        return content
    except (KeyError, IndexError, ConnectionError, ValueError) as e:
        print(f"Erro ao processar sugestão de plano de tópico: {e}")
        return "Não foi possível gerar o plano de estudo no momento. Tente novamente mais tarde."


def sugerir_subtopicos(topico: Topic) -> List[str]:
    """
    Gera uma lista de subtópicos para um tópico principal.
    """
    prompt = (
        f"Com base no tópico '{topico.title}' da disciplina de '{topico.course.title}', "
        "gere uma lista com 5 a 7 subtópicos essenciais que um estudante precisa dominar. "
        "Retorne EXCLUSIVAMENTE um objeto JSON com uma única chave 'subtopicos' contendo uma lista de strings. "
        "Exemplo: {\"subtopicos\": [\"Subtópico 1\", \"Subtópico 2\"]}"
    )
    
    try:
        api_response = _call_deepseek_api(prompt, is_json_output=True)
        # Decodifica o conteúdo JSON da resposta
        content_json = json.loads(api_response['choices'][0]['message']['content'])
        return content_json.get("subtopicos", [])
    except (KeyError, IndexError, json.JSONDecodeError, ConnectionError, ValueError) as e:
        print(f"Erro ao processar sugestão de subtópicos: {e}")
        return []


def gerar_quiz_completo(topico: Topic, num_faceis: int = 7, num_moderadas: int = 7, num_dificeis: int = 6) -> Optional[Dict[str, Any]]:
    """
    Gera um quiz completo (título, descrição e perguntas) sobre um tópico.
    """
    total_perguntas = num_faceis + num_moderadas + num_dificeis
    prompt = (
        "Aja como um professor universitário que é elaborador de provas. Crie um quiz completo sobre o tópico "
        f"'{topico.title}' da disciplina '{topico.course.title}'. "
        f"Gere exatamente {total_perguntas} perguntas de múltipla escolha (A, B, C, D), sendo "
        f"{num_faceis} fáceis, {num_moderadas} moderadas e {num_dificeis} difíceis. "
        "Retorne um único objeto JSON com as seguintes chaves: 'quiz_title' (string), "
        "'quiz_description' (string), e 'questions' (uma lista de objetos). "
        "Cada objeto de pergunta deve ter as chaves: 'question_text' (string), "
        "'choices' (um objeto com chaves 'A', 'B', 'C', 'D'), 'correct_answer' (string, a letra da chave correta), "
        "'difficulty' (string: 'EASY', 'MODERATE', ou 'HARD'), e 'explanation' (string, uma breve justificativa)."
    )

    try:
        api_response = _call_deepseek_api(prompt, is_json_output=True)
        # Decodifica o conteúdo JSON da resposta
        content_json = json.loads(api_response['choices'][0]['message']['content'])
        # Validação básica da estrutura recebida
        if "quiz_title" in content_json and "questions" in content_json:
            return content_json
        else:
            print("Erro: a resposta da IA não continha as chaves esperadas 'quiz_title' e 'questions'.")
            return None
    except (KeyError, IndexError, json.JSONDecodeError, ConnectionError, ValueError) as e:
        print(f"Erro ao processar geração de quiz: {e}")
        return None


def responder_pergunta_de_estudo(pergunta_usuario: str, historico_conversa: List[Dict[str, str]], topico_contexto: Optional[Topic] = None) -> str:
    """
    Responde a uma pergunta de um usuário no chat de estudo.
    """
    contexto_disciplina = f"O usuário está estudando o tópico '{topico_contexto.title}' da disciplina '{topico_contexto.course.title}'." if topico_contexto else ""
    
    system_prompt = (
        "Você é o 'StudyBot', um tutor de estudos amigável, paciente e especialista. "
        "Responda às perguntas dos usuários de forma clara, concisa e com exemplos práticos quando apropriado. "
        f"{contexto_disciplina}"
    )

    # Monta o histórico de mensagens para a API
    mensagens = [{"role": "system", "content": system_prompt}]
    mensagens.extend(historico_conversa)
    mensagens.append({"role": "user", "content": pergunta_usuario})

    # Para esta função, a chamada é um pouco diferente, pois já estamos passando o histórico
    payload = {
        "model": "deepseek-chat",
        "messages": mensagens
    }

    try:
        response = requests.post(DEEPSEEK_API_URL, headers=HEADERS, json=payload, timeout=60)
        response.raise_for_status()
        api_response = response.json()
        return api_response['choices'][0]['message']['content']
    except (requests.exceptions.RequestException, KeyError, IndexError) as e:
        print(f"Erro ao processar resposta do chat: {e}")
        return "Desculpe, não consegui processar sua pergunta no momento. Por favor, tente novamente."

def distribuir_subtopicos_no_cronograma(
    topico: Topic,
    subtopicos: List[str],
    planos_de_estudo: List[StudyPlan]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Distribui uma lista de subtópicos em um cronograma de estudo semanal,
    baseado nos planos de estudo do usuário e em estimativas de tempo da IA.

    Args:
        topico: O objeto Topic principal.
        subtopicos: Uma lista de strings com os títulos dos subtópicos.
        planos_de_estudo: Uma QuerySet ou lista de objetos StudyPlan do usuário
                         para a disciplina em questão.

    Returns:
        Um dicionário representando o cronograma, com os dias da semana como chaves.
        Ex: {"Segunda-feira": [{"subtopic": "Derivadas", "estimated_time": 45}]}
    """
    if not subtopicos or not planos_de_estudo:
        return {}

    # 1. CHAMAR A IA PARA ESTIMAR O TEMPO E DIFICULDADE DE CADA SUBTÓPICO
    prompt = (
        "Aja como um planejador de estudos especialista. Para o tópico principal "
        f"'{topico.title}', analise a seguinte lista de subtópicos: {json.dumps(subtopicos)}. "
        "Primeiro, ordene esta lista de subtópicos em uma sequência lógica de aprendizado, do mais básico e fundamental para o mais avançado e complexo. "
        "Depois, para cada subtópico na ordem correta, estime o tempo de estudo necessário em minutos (múltiplos de 15, como 30, 45, 60) "
        "e classifique sua dificuldade (Fácil, Médio, Difícil). "
        "Retorne EXCLUSIVAMENTE um objeto JSON com uma chave 'analise_subtopicos' contendo a lista de objetos JÁ ORDENADA. "
        "Cada objeto deve ter as chaves: 'subtopic' (string), 'estimated_time' (int), e 'difficulty' (string)."
    )

    try:
        api_response = _call_deepseek_api(prompt, is_json_output=True)
        conteudo_json = json.loads(api_response['choices'][0]['message']['content'])
        subtopicos_analisados = conteudo_json.get("analise_subtopicos", [])
        
        if not subtopicos_analisados:
            print("Erro: A análise da IA não retornou subtópicos.")
            return {}
            
    except (KeyError, IndexError, json.JSONDecodeError, ConnectionError, ValueError) as e:
        print(f"Erro ao analisar subtópicos com a IA: {e}")
        return {}

    # 2. PREPARAR O CRONOGRAMA E OS BLOCOS DE ESTUDO
    
    # Mapeia o número do dia da semana para o nome (ex: 0 -> 'Segunda-feira')
    dias_semana_map = dict(StudyPlan.DayOfWeek.choices)
    
    # Cria a estrutura do cronograma semanal do usuário com o tempo disponível
    cronograma_disponivel = {dia_nome: 0 for dia_num, dia_nome in dias_semana_map.items()}
    for plano in planos_de_estudo:
        dia_nome = dias_semana_map.get(plano.day_of_week)
        if dia_nome:
            cronograma_disponivel[dia_nome] += plano.minutes_planned
            
    # Cria a estrutura do resultado final
    cronograma_final = {dia: [] for dia in cronograma_disponivel.keys()}
    
    # Fila de subtópicos para distribuir
    fila_subtopicos = list(subtopicos_analisados)

    # 3. DISTRIBUIR OS SUBTÓPICOS NOS DIAS DISPONÍVEIS (LÓGICA PYTHON)
    for dia_num in sorted(dias_semana_map.keys()): # Itera na ordem dos dias (Seg, Ter, Qua...)
        dia_nome = dias_semana_map[dia_num]
        tempo_restante_no_dia = cronograma_disponivel[dia_nome]
        
        # Continua alocando enquanto houver tempo no dia e subtópicos na fila
        while tempo_restante_no_dia > 0 and fila_subtopicos:
            subtopico_atual = fila_subtopicos[0] # Pega o próximo subtópico da fila
            tempo_necessario = subtopico_atual.get("estimated_time", 30)

            if tempo_restante_no_dia >= tempo_necessario:
                # Aloca o subtópico neste dia
                cronograma_final[dia_nome].append(subtopico_atual)
                tempo_restante_no_dia -= tempo_necessario
                fila_subtopicos.pop(0) # Remove o subtópico alocado da fila
            else:
                # Não há tempo suficiente neste dia para o próximo subtópico, passa para o próximo dia
                break
    
    if fila_subtopicos:
        print(f"Aviso: Não foi possível alocar todos os subtópicos. {len(fila_subtopicos)} restantes.")
        # Em uma implementação real, você poderia lidar com isso (ex: sugerir aumentar o tempo de estudo)

    return cronograma_final