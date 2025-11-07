from aws_cdk import Stack, CfnOutput, RemovalPolicy, aws_cognito as cognito
from constructs import Construct
from cdk_nag import NagSuppressions


class AuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Cognito User Pool
        self.user_pool = cognito.UserPool(
            self,
            "LlmStreamingUserPool",
            user_pool_name="llm-streaming-user-pool",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            mfa=cognito.Mfa.OPTIONAL,  # Making it optional for demo, but available
            mfa_second_factor=cognito.MfaSecondFactor(sms=False, otp=True),
            # Note: Advanced security mode requires Cognito Plus plan ($0.05 per MAU)
            # Removed for demo purposes - would be enabled in production
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,  # For demo purposes
        )

        # Create User Pool Client
        self.user_pool_client = cognito.UserPoolClient(
            self,
            "LlmStreamingUserPoolClient",
            user_pool=self.user_pool,
            generate_secret=False,  # For web clients
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
            ),
        )

        # Output values for easy reference
        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID",
        )

        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
            description="Cognito User Pool Client ID",
        )

        # Add CDK-Nag suppressions for acceptable findings
        NagSuppressions.add_resource_suppressions(
            self.user_pool,
            [
                {
                    "id": "AwsSolutions-COG3",
                    "reason": "Advanced Security Mode requires Cognito Plus plan ($0.05 per MAU). Disabled for demo purposes to avoid additional costs. Would be enabled in production environments.",
                }
            ],
        )
