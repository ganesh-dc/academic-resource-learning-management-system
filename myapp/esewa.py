# myapp/esewa.py
import base64
import hashlib

class EsewaConfig:
    # ========== SANDBOX CREDENTIALS (FOR TESTING) ==========
    ESewa_URL = "https://rc-epay.esewa.com.np/api/epay/main/v2/form"
    MERCHANT_ID = "epay_test"
    SECRET_KEY = "8gBm/:&EnhH.1/q"
    PRODUCT_CODE = "EPAYTEST"
    
    @staticmethod
    def generate_signature(total_amount, transaction_uuid, product_code):
        """Generate HMAC SHA256 signature as per eSewa docs"""
        message = f"total_amount={total_amount},transaction_uuid={transaction_uuid},product_code={product_code}"
        secret_key = EsewaConfig.SECRET_KEY.encode('utf-8')
        message = message.encode('utf-8')
        
        # Create HMAC SHA256 signature
        import hmac
        signature = hmac.new(secret_key, message, hashlib.sha256).digest()
        return base64.b64encode(signature).decode('utf-8')
    
    @staticmethod
    def get_esewa_payload(amount, transaction_uuid, success_url, failure_url):
        """Prepare data for eSewa payment"""
        return {
            "amount": str(amount),
            "tax_amount": "0",
            "total_amount": str(amount),
            "transaction_uuid": transaction_uuid,
            "product_code": EsewaConfig.PRODUCT_CODE,
            "product_service_charge": "0",
            "product_delivery_charge": "0",
            "success_url": success_url,
            "failure_url": failure_url,
            "signed_field_names": "total_amount,transaction_uuid,product_code",
            "signature": EsewaConfig.generate_signature(
                str(amount), 
                transaction_uuid, 
                EsewaConfig.PRODUCT_CODE
            )
        }