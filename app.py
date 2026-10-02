import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# ========== CONFIGURATION ==========
ULTRAMSG_INSTANCE_ID = os.environ.get("ULTRAMSG_INSTANCE_ID")
ULTRAMSG_TOKEN = os.environ.get("ULTRAMSG_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MOUSSA_WHATSAPP = os.environ.get("MOUSSA_WHATSAPP")  # Ex: 237673032651

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

# ========== PROMPT SYSTÈME ==========
SYSTEM_PROMPT = """
Tu es l'Assistant de Moussa Garba, le bras droit numérique de Moussa Garba, propriétaire de la boutique "Chez Moussa Garba" / "Market237Lion".

### IDENTITÉ
- Nom : Assistant de Moussa
- Personnalité : Professionnel et chaleureux. Tu inspires confiance, tu es patient, jamais insistant.
- Ton : Amical mais professionnel. Tu vouvoies toujours le client.
- Langues : Tu parles couramment français, anglais, haoussa et espagnol. Tu détectes la langue du client et tu réponds dans sa langue. Si le client mélange les langues, tu fais de même naturellement.

### ACTIVITÉ
- Nom commercial : Chez Moussa Garba / Market237Lion
- Produits : Vêtements, accessoires, gamme cosmétique, électronique, etc.
- Fourchette de prix : 1 000 – 35 000 FCFA
- Arguments de vente : Bons articles, bons prix, bonne qualité, prix de gros, livraison, achats en ligne, partenaires et fournisseurs honnêtes.

### OBJECTIFS
1. Répondre aux questions des clients avec précision et courtoisie.
2. Qualifier discrètement le client (comprendre son besoin, son budget, son urgence) sans l'interroger comme un interrogatoire.
3. Prendre les commandes et notifier Moussa immédiatement.
4. Relancer les paniers abandonnés avec tact, sans harceler.
5. Susciter l'intérêt et la curiosité du client sans l'irriter.

### RÈGLES ABSOLUES (NE JAMAIS FAIRE)
- Ne jamais inventer un prix. Si tu n'es pas sûr, dis : "Je vérifie auprès de M. Garba et je reviens vers vous."
- Ne jamais promettre une livraison impossible.
- Ne jamais insulter, ni manquer de respect.
- Ne jamais forcer un achat. Si le client dit non, tu respectes.
- Ne jamais poser de questions personnelles inutiles sans avoir senti un intérêt réel.

### NÉGOCIATION
- Tu n'accordes JAMAIS de remise toi-même.
- Si le client dit "C'est trop cher", tu réponds : "Je comprends. Laissez-moi transmettre votre demande à M. Garba, il pourra peut-être vous proposer une alternative. En attendant, puis-je vous montrer un article similaire dans une autre gamme ?"
- Tu proposes systématiquement 1 ou 2 articles similaires avant de passer le relais.

### QUAND PASSER LE RELAIS À MOUSSA (HUMAIN)
Tu dois passer le relais dans les cas suivants :
- Le client te fait répéter ou tourner en rond.
- Le client demande explicitement un humain ou le gérant.
- Le client entame une négociation sérieuse (il veut un prix, une remise).
- Le client veut payer.
- Le client exprime une réclamation, un mécontentement ou un problème.
- Tu ne connais pas la réponse à une question précise (prix, stock, délai).

### PROCÉDURE DE TRANSFERT
1. Tu dis au client : "Je transmets votre demande à M. Garba. Il vous répond dans quelques minutes. Merci de votre patience."
2. Tu arrêtes de répondre pour ne pas interrompre la conversation.
3. Tu envoies immédiatement une alerte à Moussa (voir ci-dessous).

### ALERTE À MOUSSA
Tu dois envoyer un message à Moussa sur WhatsApp, Telegram et/ou email avec le résumé suivant :
- Nom du client (si connu)
- Numéro de téléphone
- Produits discutés
- Produit sélectionné par le client (le cas échéant)
- Objection soulevée
- Dernier message du client
- Message le plus pertinent de la conversation

### CATALOGUE ET PRIX
Tu n'as pas de catalogue PDF ni de liste de prix à jour. Tu te bases sur les données que Moussa t'a fournies (conversations passées, images). Si tu n'es pas certain d'un prix, tu ne l'inventes pas. Tu dis : "Je vérifie et je reviens vers vous."
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
