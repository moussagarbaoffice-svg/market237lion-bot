### TON STYLE DE RÉPONSE
- Réponses courtes (2-3 phrases maximum), sauf si le client demande des détails.
- Utilise des emojis avec modération (1 maximum par message).
- Sois rassurant, jamais pressant.
- Termine toujours par une question ouverte pour garder la conversation vivante.

### EXEMPLE DE DÉMARRAGE
Client : "Bonjour, vous avez des sacs à main ?"
Toi : "Bonjour ! Oui, nous avons plusieurs modèles de sacs à main. Quel style recherchez-vous ? (élégant, pratique, tendance) 🙂"
"""

# ========== MÉMOIRE DES CONVERSATIONS ==========
conversations = {}

def get_conversation(chat_id):
    if chat_id not in conversations:
        conversations[chat_id] = []
    return conversations[chat_id]

def add_to_conversation(chat_id, role, message):
    conversations[chat_id].append({"role": role, "content": message})
    if len(conversations[chat_id]) > 20:
        conversations[chat_id] = conversations[chat_id][-20:]

# ========== DÉTECTION DE TRANSFERT ==========
TRANSFER_KEYWORDS = [
    "humain", "gérant", "responsable", "patron", "moussa",
    "trop cher", "négocier", "remise", "réduction",
    "payer", "paiement", "mobile money", "orange money", "mtn",
    "réclamation", "problème", "remboursement", "arnaque"
]

def needs_transfer(message):
    msg = message.lower()
    return any(keyword in msg for keyword in TRANSFER_KEYWORDS)

# ========== ENVOI DE MESSAGE ==========
def send_whatsapp(to, body):
    url = f"https://api.ultramsg.com/{ULTRAMSG_INSTANCE_ID}/messages/chat"
    payload = {
        "token": ULTRAMSG_TOKEN,
        "to": to,
        "body": body
    }
    response = requests.post(url, data=payload)
    return response.json()

# ========== NOTIFICATION À MOUSSA ==========
def notify_moussa(client_name, client_number, products, objection, last_message):
    alert = (
        f"🔔 NOUVEAU TRANSFERT\n\n"
        f"Client : {client_name}\n"
        f"Numéro : {client_number}\n"
        f"Produits discutés : {products}\n"
        f"Objection : {objection}\n"
        f"Dernier message : {last_message}"
    )
    send_whatsapp(MOUSSA_WHATSAPP, alert)

# ========== WEBHOOK PRINCIPAL ==========
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    
    if not data or "data" not in data:
        return jsonify({"status": "ignored"}), 200
    
    message_data = data["data"]
    chat_id = message_data.get("from")
    body = message_data.get("body", "")
    sender_name = message_data.get("senderName", "Client")
    
    if not chat_id or not body:
        return jsonify({"status": "ignored"}), 200
    
    if needs_transfer(body):
        send_whatsapp(chat_id, "Je transmets votre demande à M. Garba. Il vous répond dans quelques minutes. Merci de votre patience.")
        notify_moussa(sender_name, chat_id, "À préciser", "Négociation / Demande humaine", body)
        return jsonify({"status": "transferred"}), 200
    
    history = get_conversation(chat_id)
    add_to_conversation(chat_id, "user", body)
    
    prompt = SYSTEM_PROMPT + "\n\nHistorique de la conversation :\n"
    for msg in history:
        prompt += f"{msg['role']}: {msg['content']}\n"
    prompt += f"\nClient : {body}\nAssistant :"
    
    try:
        response = model.generate_content(prompt)
        ai_reply = response.text.strip()
    except Exception as e:
        ai_reply = "Je suis désolé, je rencontre un petit souci technique. Je transmets votre message à M. Garba."
        notify_moussa(sender_name, chat_id, "Erreur technique", str(e), body)
    
    add_to_conversation(chat_id, "assistant", ai_reply)
    send_whatsapp(chat_id, ai_reply)
    
    return jsonify({"status": "ok"}), 200

if name == "main":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
