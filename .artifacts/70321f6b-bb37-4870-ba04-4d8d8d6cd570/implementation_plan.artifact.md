# Plano de Implementação: Arquitetura Hilt e Refatoração Inicial

Este plano descreve a integração do Hilt (Dependency Injection) no projeto DDS, estabelecendo a base para uma arquitetura modular, testável e escalável.

## User Review Required

> [!IMPORTANT]
> A introdução do Hilt altera a forma como os ViewModels e instâncias do Firebase são criados. Após as mudanças, o Android Studio precisará de um Gradle Sync completo.

## Proposed Changes

### [Infraestrutura] Configuração do Hilt

#### [MODIFY] [libs.versions.toml](file:///D:/programas/DDS/gradle/libs.versions.toml)
Adicionar as versões e bibliotecas do Hilt (Dagger Hilt).

#### [MODIFY] [build.gradle.kts (Root)](file:///D:/programas/DDS/build.gradle.kts)
Adicionar o plugin do Hilt ao projeto.

#### [MODIFY] [build.gradle.kts (App)](file:///D:/programas/DDS/app/build.gradle.kts)
Aplicar o plugin `dagger.hilt.android.plugin` e adicionar as dependências do Hilt.

---

### [Core] Inicialização e Injeção

#### [MODIFY] [app.kt](file:///D:/programas/DDS/app/src/main/java/com/chicoeletro/dds/app.kt)
Anotar a classe `App` com `@HiltAndroidApp` para habilitar a geração de código do Hilt.

#### [MODIFY] [MainActivity.kt](file:///D:/programas/DDS/app/src/main/java/com/chicoeletro/dds/MainActivity.kt)
Anotar a `MainActivity` com `@AndroidEntryPoint` para permitir a injeção de dependências.

#### [NEW] [FirebaseModule.kt](file:///D:/programas/DDS/app/src/main/java/com/chicoeletro/dds/di/FirebaseModule.kt)
Criar um módulo Hilt para prover instâncias do FirebaseAuth, Firestore, Database e Storage.

#### [NEW] [AppModule.kt](file:///D:/programas/DDS/app/src/main/java/com/chicoeletro/dds/di/AppModule.kt)
Criar um módulo para prover o Contexto da aplicação e outras dependências globais (como o DataStore).

---

### [Feature] Migração de ViewModel (Exemplo)

#### [MODIFY] [TrainingViewModel.kt](file:///D:/programas/DDS/app/src/main/java/com/chicoeletro/dds/viewmodel/TrainingViewModel.kt)
Converter o ViewModel para usar `@HiltViewModel` e injeção de construtor.

## Verification Plan

### Automated Tests
- Executar `./gradlew assembleDebug` para verificar se a geração de código do Hilt está funcionando corretamente.
- Verificar se o App inicializa sem crashes relacionados à injeção.

### Manual Verification
- Abrir o app e verificar se os treinamentos carregam corretamente (confirmando que a injeção do Firebase/Repository no ViewModel funcionou).
- Testar a navegação básica para garantir que o `@AndroidEntryPoint` na Activity não causou efeitos colaterais.
